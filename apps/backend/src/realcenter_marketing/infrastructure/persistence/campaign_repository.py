"""Filesystem implementation preserving the existing run layout and media IDs."""
import base64
import json
from pathlib import Path
from uuid import uuid4

from realcenter_marketing.application.commands import RunRequest
from realcenter_marketing.domain.campaigns import Campaign
from realcenter_marketing.infrastructure.observability.journal import RunJournal
from realcenter_marketing.infrastructure.uploads import decode_upload
from realcenter_marketing.infrastructure.references import catalog as reference_catalog, reference_file
from .filesystem import media_catalog, read_json, run_directory


class FileCampaignRepository:
    def __init__(self, root):
        self.root = root.resolve()

    decode_upload = staticmethod(decode_upload)

    def _input_entry(self, key):
        # /api/media retains its legacy IDs. /api/references (including newly added
        # products) returns a different, content-based ID. Accept both contracts
        # without duplicating entries or changing existing media URLs.
        entry = media_catalog(self.root).get(key)
        if entry is not None:
            return entry
        item = next((item for item in reference_catalog(self.root) if item['id'] == key), None)
        if item is not None:
            return {'path': reference_file(self.root, key), 'product': item['kind'] == 'product'}
        return None

    def prepare_inputs(self, request):
        upload = decode_upload(request.upload)
        reference = decode_upload(request.reference_upload)
        product = None
        if request.product_id:
            entry = self._input_entry(request.product_id)
            if not entry or not entry['product']:
                raise ValueError('Selecione uma foto válida do catálogo')
            product = entry['path']
        # A reference chosen from the library resolves to the same bytes an upload would
        # have carried, so everything downstream stays identical.
        if reference is None and getattr(request, 'reference_id', None):
            entry = self._input_entry(request.reference_id)
            if not entry:
                raise ValueError('Selecione uma referência válida do catálogo')
            reference = Path(entry['path']).read_bytes()
        return upload, reference, product

    def set_title(self, run_id, title):
        """A name the store chose, kept beside the run rather than in the journal.

        events.jsonl is append-only and read in full on every poll; a rename is not an
        event of the execution and does not belong in that stream.
        """
        directory = self.root / 'campaigns' / 'runs' / run_id
        if not directory.is_dir():
            raise ValueError('Campanha não encontrada')
        target = directory / 'title.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps({'title': title}, ensure_ascii=False), encoding='utf-8')
        temporary.replace(target)
        return title

    def create_run(self, request, inputs):
        upload, reference, product = inputs
        journal = RunJournal(self.root / 'campaigns' / 'runs' / f'run-{uuid4().hex}')
        if reference:
            self._save_input(journal, 'reference', reference)
        if upload:
            product = self._save_input(journal, 'product', upload)
        elif product:
            product = self._save_input(journal, 'product', product.read_bytes())
        return journal, product

    @staticmethod
    def _save_input(journal, name, content):
        path = journal.directory / (name + ('.png' if content.startswith(b'\x89PNG') else '.jpg'))
        path.write_bytes(content)
        return path

    def create_consultation(self):
        return RunJournal(self.root / 'consultations' / uuid4().hex)

    def create_assist(self):
        return RunJournal(self.root / 'campaigns' / 'brief-assists' / uuid4().hex)

    def saved_request(self, run_id):
        directory = run_directory(self.root, run_id)
        if not directory.is_dir():
            raise ValueError('Campanha não encontrada')
        campaign = read_json(directory / 'campaign.json', {})
        brief = read_json(directory / 'brief.json') or campaign.get('brief')
        if not brief:
            raise ValueError('Esta campanha não tem briefing salvo para repetir')
        first = next((e for e in self._events(directory) if e['event'] == 'run_started'), {})
        request = RunRequest(**brief, mode=first.get('mode', campaign.get('execution_mode', 'live')),
                             generate_image=first.get('image_requested', any(e['event'] == 'image_started' for e in self._events(directory))))
        for prefix, field in [('product', 'upload'), ('reference', 'reference_upload')]:
            file = next((directory / (prefix + ext) for ext in ('.png', '.jpg') if (directory / (prefix + ext)).is_file()), None)
            if file:
                setattr(request, field, base64.b64encode(file.read_bytes()).decode())
        return request

    @staticmethod
    def _events(directory):
        path = directory / 'events.jsonl'
        if not path.exists():
            return []
        result = []
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict): result.append(value)
            except ValueError:
                pass
        return result

    def last_event(self, run_id):
        events = self._events(run_directory(self.root, run_id))
        return events[-1].get('event') if events else None

    def has_campaign(self, run_id):
        return bool(read_json(run_directory(self.root, run_id) / 'campaign.json'))

    def campaign(self, run_id):
        return Campaign.model_validate(read_json(run_directory(self.root, run_id) / 'campaign.json'))

    def delete(self, run_id):
        directory = run_directory(self.root, run_id)
        if not directory.is_dir():
            raise ValueError('Campanha não encontrada')
        trash = (self.root / 'campaigns' / 'runs' / '.trash').resolve()
        if not trash.is_relative_to((self.root / 'campaigns' / 'runs').resolve()):
            raise ValueError('Destino de exclusão inválido')
        trash.mkdir(exist_ok=True)
        directory.rename(trash / (run_id + '-' + uuid4().hex))

    def resume(self, run_id):
        return RunJournal.resume(run_directory(self.root, run_id))

    def usage(self, journal):
        return read_json(journal.directory / 'usage.json')

    def product(self, run_id):
        directory = run_directory(self.root, run_id)
        return next((directory / name for name in ('product.png', 'product.jpg') if (directory / name).exists()), None)

    def revision_image(self, run_id, image_id):
        entry = media_catalog(self.root).get(image_id)
        if not entry or entry['run_id'] != run_id or not entry['name'].startswith(('feed-', 'story-', 'carousel-', 'reel_cover-')):
            raise ValueError('Selecione uma arte desta campanha para editar')
        return entry['path']

    def save_revision(self, journal, content):
        directory = journal.directory / 'revision-inputs'
        directory.mkdir(exist_ok=True)
        path = directory / (uuid4().hex + ('.png' if content.startswith(b'\x89PNG') else '.jpg'))
        path.write_bytes(content)
        return path

    def image_metadata(self, image):
        return read_json(image.with_suffix('.json'), {})

    def carousel_files(self, journal):
        return read_json(journal.directory / 'carousel.json', {'files': {}})

    def existing_image(self, journal, filename):
        if not filename:
            return None
        path = (journal.directory / filename).resolve()
        if not path.is_relative_to(journal.directory.resolve()):
            raise ValueError('Imagem fora da campanha')
        return path if path.is_file() else None

    def save_carousel(self, journal, batch):
        temporary = journal.directory / 'carousel.tmp'
        temporary.write_text(json.dumps(batch), encoding='utf-8')
        temporary.replace(journal.directory / 'carousel.json')
