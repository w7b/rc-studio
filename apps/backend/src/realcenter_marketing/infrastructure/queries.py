from realcenter_marketing.application.diagnostics import report
from . import references
from .persistence.filesystem import snapshot, media_catalog, read_json, run_directory, OUTPUTS
from .persistence.campaign_repository import FileCampaignRepository
from .system_catalog import system_activity, usage_audit


class LocalStudioQueries:
    def __init__(self, root):
        self.root = root

    def runs(self, active_id):
        return snapshot(self.root, active_id)

    def media(self):
        return [{k: m[k] for k in ('id', 'name', 'url', 'product', 'run_id', 'created_at')}
                for m in media_catalog(self.root).values()]

    def media_file(self, key):
        entry = media_catalog(self.root).get(key)
        if not entry:
            raise ValueError('Mídia não encontrada')
        return entry['path'].read_bytes(), entry['name']

    def references(self):
        return references.catalog(self.root)

    def reference_file(self, key):
        path = references.reference_file(self.root, key)
        return path.read_bytes(), path.name

    def save_reference(self, request):
        return references.save_reference(self.root, request)

    def activity(self):
        return system_activity(self.root)

    def usage(self):
        return usage_audit(self.root)

    def artifact(self, run_id, name):
        directory = run_directory(self.root, run_id)
        if not directory.is_dir():
            raise ValueError('Execução não encontrada')
        if name == 'diagnostics.json':
            if not (directory / 'events.jsonl').is_file():
                raise ValueError('Diagnóstico não encontrado')
            events = FileCampaignRepository._events(directory)
            outputs = {role: True for role in OUTPUTS if (directory / (role + '.json')).is_file()}
            return report(run_id, events, read_json(directory / 'usage.json'), outputs), 'application/json; charset=utf-8'
        allowed = {role + '.json' for role in OUTPUTS} | {'legenda-feed.txt', 'events.jsonl', 'image-prompt.txt', 'usage.json'}
        if name not in allowed or not (directory / name).is_file():
            raise ValueError('Arquivo não encontrado')
        return (directory / name).read_bytes(), 'application/octet-stream'
