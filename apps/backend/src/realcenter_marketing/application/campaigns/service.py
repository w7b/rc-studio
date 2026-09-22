"""Campaign commands. All side effects are supplied through application ports."""
import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from realcenter_marketing.application.commands import ImageRequest, RunRequest
from realcenter_marketing.application.diagnostics import error_details
from realcenter_marketing.application.errors import BusyError, public_error
from realcenter_marketing.application.images import ImageWorkflow
from realcenter_marketing.domain.campaigns import CampaignBrief
from .ports import CampaignExecutor, CampaignRepository, ExecutionScheduler, JobQueue


@dataclass
class Admission:
    kind: str
    request: object
    journal: object
    product: object = None
    brief: object = None
    campaign: object = None
    base_image: object = None
    revision_reference: object = None
    ticket: object = None

    @property
    def run_id(self):
        return self.journal.directory.name


class CampaignService:
    def __init__(self, repository: CampaignRepository, scheduler: ExecutionScheduler,
                 execute: CampaignExecutor, improve_brief: Callable,
                 images: ImageWorkflow, validate_live: Callable[..., None], quota=None,
                 queue: JobQueue | None = None):
        self.repository, self.scheduler = repository, scheduler
        self.execute, self.improve_brief = execute, improve_brief
        self.images, self.validate_live = images, validate_live
        # None means unmetered, which is what a standalone install is.
        self.quota = quota
        self.queue = queue
        self.active_id = None

    @property
    def lock(self):
        return self.scheduler.lock

    @property
    def busy(self):
        # Briefing consultations hold the same slot without creating a campaign ID.
        return self.lock.locked()

    def _reserve(self, **amounts):
        """Reserve before anything is spent. A crash after this point leaves the unit
        counted, which is the conservative direction when the operator pays the bill."""
        return self.quota.reserve(**amounts) if self.quota else None

    def _claim(self, message='Já existe uma execução em andamento'):
        if not self.scheduler.acquire():
            raise BusyError(message)

    def _release(self):
        self.active_id = None
        self.scheduler.release()

    def _claim_and_reserve(self, message='Já existe uma execução em andamento', **amounts):
        self._claim(message)
        try:
            return self._reserve(**amounts) if amounts else None
        except BaseException:
            self._release()
            raise

    def assist(self, request):
        self.validate_live(request)
        if not request.request.strip():
            raise ValueError('Escreva uma ideia para o Creative Producer melhorar')
        ticket = self._claim_and_reserve(
            'Uma consulta de briefing ou campanha já está em andamento. Aguarde sua conclusão.',
            assists=1)
        journal = None
        provider_started = False
        try:
            journal = self.repository.create_assist()
            journal.save('original', request)
            provider_started = True
            result = asyncio.run(self.improve_brief(request, journal))
            journal.save('suggestion', result)
            journal.emit('assist_completed', 'Creative Producer')
            return {'suggestion': result.model_dump(), 'usage': self.repository.usage(journal)}
        except Exception as exc:
            if journal:
                journal.emit('assist_failed', 'Creative Producer', **error_details(exc))
            raise ValueError('Não foi possível melhorar o briefing. ' + public_error(exc)) from None
        finally:
            if ticket and not provider_started:
                ticket.void()
            self._release()

    def saved_request(self, run_id):
        return self.repository.saved_request(run_id)

    def retry(self, run_id):
        if self.busy or (self.queue is not None and self.queue.pending()):
            raise BusyError('Já existe uma execução em andamento')
        if self.repository.last_event(run_id) == 'run_completed':
            raise ValueError('A campanha já está concluída; use Editar')
        if self.repository.has_campaign(run_id):
            self.image(run_id)
            return run_id
        return self.start(self.saved_request(run_id))

    def set_title(self, run_id, title):
        """Renaming touches no provider and no quota, so it never waits on the slot."""
        return self.repository.set_title(run_id, title.strip())

    def delete(self, run_id):
        self._check_pending()
        self._claim('Aguarde a execução terminar antes de excluir')
        try:
            self.repository.delete(run_id)
        finally:
            self._release()

    def start(self, request):
        return self.dispatch(self.admit(request))

    def _check_pending(self):
        if self.queue is not None and self.queue.pending():
            raise BusyError('Já existe uma execução em andamento')

    def admit(self, request):
        self._check_pending()
        brief = CampaignBrief(request=request.request, confirmed_facts=request.confirmed_facts,
                              publication=request.publication, family=request.family)
        if request.mode == 'live':
            self.validate_live(request)
        if request.mode == 'demo' and request.generate_image:
            raise ValueError('Demonstração não gera imagens com IA')
        amounts = ({'campaigns': 1,
                    'images': request.publication.slides if request.generate_image else 0}
                   if request.mode == 'live' else {})
        ticket = self._claim_and_reserve(**amounts)
        try:
            inputs = self.repository.prepare_inputs(request)
            journal, product = self.repository.create_run(request, inputs)
            self.active_id = journal.directory.name
            journal.save('brief', brief)
            journal.emit('run_started', mode=request.mode, image_requested=request.generate_image,
                         model=request.model_id, image_model=request.image_model_id)
            return Admission('campaign', request, journal, product, brief=brief, ticket=ticket)
        except BaseException:
            # Nothing reached a provider, so the reservation is handed back.
            if ticket:
                ticket.void()
            self._release()
            raise

    def dispatch(self, admission):
        try:
            if self.queue is None:
                self.scheduler.submit(lambda: self._run_local(admission))
            else:
                # Publish the event before the job becomes claimable. A fast worker
                # must never have run_completed overwritten by a late run_queued.
                admission.journal.emit('run_queued')
                self.queue.enqueue(admission.kind, self._payload(admission), admission.run_id)
            return admission.run_id
        except BaseException as exc:
            if admission.ticket:
                admission.ticket.void()
            if self.queue is None:
                self._release()
            else:
                admission.journal.emit('run_failed', message=public_error(exc))
            raise
        finally:
            if self.queue is not None:
                self._release()

    @staticmethod
    def _payload(admission):
        request = admission.request.model_copy(update={
            key: None for key in ('upload', 'reference_upload')
            if hasattr(admission.request, key)})
        ticket = admission.ticket
        relative = lambda path: path.relative_to(admission.journal.directory).as_posix() if path else None
        return {'request': request.model_dump(mode='json'),
                'base_image': relative(admission.base_image),
                'revision_reference': relative(admission.revision_reference),
                'reservation': {'tenant_id': ticket.tenant_id, 'period': ticket.period,
                                'amounts': dict(ticket.amounts)} if ticket else None}

    def _run_local(self, admission):
        try:
            self.run(admission)
        except Exception:
            # run() persisted the failure. Keep the standalone scheduler thread alive.
            pass

    def run(self, admission):
        request, journal, product = admission.request, admission.journal, admission.product
        try:
            if admission.kind == 'campaign':
                campaign = asyncio.run(self.execute(admission.brief, request.mode, journal, request.model_id))
                journal.save('campaign', campaign)
                if request.generate_image:
                    self._image(campaign, journal, product, model_id=request.image_model_id)
            else:
                self._image(admission.campaign, journal, product, request.changes.strip(),
                            admission.base_image, admission.revision_reference,
                            model_id=request.image_model_id)
            journal.emit('run_completed')
        except Exception as exc:
            journal.emit('run_failed', journal.current_agent, **error_details(exc), message=public_error(exc))
            raise
        finally:
            self._release()

    def _image(self, campaign, journal, product, changes='', base_image=None,
               revision_reference=None, model_id=None):
        return self.images.execute(campaign, journal, product, changes, base_image,
                                   revision_reference, model_id=model_id)

    def image(self, run_id, request=None):
        return self.dispatch(self.admit_image(run_id, request))

    def admit_image(self, run_id, request=None):
        self._check_pending()
        request = request or ImageRequest()
        reference = self.repository.decode_upload(request.reference_upload)
        base_image = None
        if request.base_image_id:
            base_image = self.repository.revision_image(run_id, request.base_image_id)
            if not request.changes.strip():
                raise ValueError('Descreva as alterações desejadas')
        elif request.changes.strip() or reference:
            raise ValueError('Selecione a imagem base da edição')
        campaign = self.repository.campaign(run_id)
        if campaign.execution_mode != 'live':
            raise ValueError('A demonstração não pode gerar uma imagem de campanha real')
        self.validate_live(request)
        ticket = self._claim_and_reserve(images=1)
        try:
            journal = self.repository.resume(run_id)
            product = self.repository.product(run_id)
            self.active_id = run_id

            revision = self.repository.save_revision(journal, reference) if reference else None
            return Admission('image', request, journal, product, campaign=campaign,
                             base_image=base_image, revision_reference=revision, ticket=ticket)
        except BaseException:
            if ticket:
                ticket.void()
            self._release()
            raise

    def _rehydrate(self, kind, run_id, payload):
        if kind not in ('campaign', 'image'):
            raise ValueError(f'Tipo de trabalho desconhecido: {kind}')
        try:
            journal = self.repository.resume(run_id)
        except ValueError as exc:
            raise ValueError(f'Run {run_id}: diretório indisponível; verifique a montagem '
                             'compartilhada entre web e worker. Falha permanente.') from exc
        product = self.repository.product(run_id)
        if kind == 'campaign':
            request = RunRequest.model_validate(payload['request'])
            brief = CampaignBrief(request=request.request, confirmed_facts=request.confirmed_facts,
                                  publication=request.publication, family=request.family)
            return Admission(kind, request, journal, product, brief=brief)
        request = ImageRequest.model_validate(payload['request'])
        return Admission(kind, request, journal, product, campaign=self.repository.campaign(run_id),
                         base_image=self.repository.existing_image(journal, payload.get('base_image')),
                         revision_reference=self.repository.existing_image(journal, payload.get('revision_reference')))

    def resume(self, kind, run_id, payload):
        """Worker entry: no new run, no quota reservation, no dispatch."""
        self._claim()
        try:
            admission = self._rehydrate(kind, run_id, payload)
            self.active_id = run_id
        except BaseException:
            self._release()
            raise
        return self.run(admission)

    def close(self, timeout=None):
        return self.scheduler.close(timeout)
