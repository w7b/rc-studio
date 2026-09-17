"""Campaign commands. All side effects are supplied through application ports."""
import asyncio
from collections.abc import Callable

from realcenter_marketing.application.commands import ImageRequest
from realcenter_marketing.application.diagnostics import error_details
from realcenter_marketing.application.errors import BusyError, public_error
from realcenter_marketing.application.images import ImageWorkflow
from realcenter_marketing.domain.campaigns import CampaignBrief
from .ports import CampaignExecutor, CampaignRepository, ExecutionScheduler


class CampaignService:
    def __init__(self, repository: CampaignRepository, scheduler: ExecutionScheduler,
                 execute: CampaignExecutor, improve_brief: Callable,
                 images: ImageWorkflow, validate_live: Callable[..., None]):
        self.repository, self.scheduler = repository, scheduler
        self.execute, self.improve_brief = execute, improve_brief
        self.images, self.validate_live = images, validate_live
        self.active_id = None

    @property
    def lock(self):
        return self.scheduler.lock

    def _claim(self, message='Já existe uma execução em andamento'):
        if not self.scheduler.acquire():
            raise BusyError(message)

    def _release(self):
        self.active_id = None
        self.scheduler.release()

    def assist(self, request):
        self.validate_live()
        if not request.request.strip():
            raise ValueError('Escreva uma ideia para o Creative Producer melhorar')
        self._claim('Aguarde a consulta ou campanha em andamento terminar')
        journal = None
        try:
            journal = self.repository.create_assist()
            journal.save('original', request)
            result = asyncio.run(self.improve_brief(request, journal))
            journal.save('suggestion', result)
            journal.emit('assist_completed', 'Creative Producer')
            return {'suggestion': result.model_dump(), 'usage': self.repository.usage(journal)}
        except Exception as exc:
            if journal:
                journal.emit('assist_failed', 'Creative Producer', **error_details(exc))
            raise ValueError('Não foi possível melhorar o briefing. ' + public_error(exc)) from None
        finally:
            self._release()

    def saved_request(self, run_id):
        return self.repository.saved_request(run_id)

    def retry(self, run_id):
        if self.active_id:
            raise BusyError('Já existe uma execução em andamento')
        if self.repository.last_event(run_id) == 'run_completed':
            raise ValueError('A campanha já está concluída; use Editar')
        if self.repository.has_campaign(run_id):
            self.image(run_id)
            return run_id
        return self.start(self.saved_request(run_id))

    def delete(self, run_id):
        self._claim('Aguarde a execução terminar antes de excluir')
        try:
            self.repository.delete(run_id)
        finally:
            self._release()

    def start(self, request):
        brief = CampaignBrief(request=request.request, confirmed_facts=request.confirmed_facts,
                              publication=request.publication, family=request.family)
        if request.mode == 'live':
            self.validate_live(request)
        if request.mode == 'demo' and request.generate_image:
            raise ValueError('Demonstração não gera imagens com IA')
        inputs = self.repository.prepare_inputs(request)
        self._claim()
        try:
            journal, product = self.repository.create_run(request, inputs)
            self.active_id = journal.directory.name
            journal.save('brief', brief)
            journal.emit('run_started', mode=request.mode, image_requested=request.generate_image,
                         model=request.model_id, image_model=request.image_model_id)
            run_id = self.active_id
            self.scheduler.submit(lambda: self._work(request, brief, journal, product))
            return run_id
        except BaseException:
            self._release()
            raise

    def _work(self, request, brief, journal, product):
        try:
            campaign = asyncio.run(self.execute(brief, request.mode, journal, request.model_id))
            journal.save('campaign', campaign)
            if request.generate_image:
                self._image(campaign, journal, product, model_id=request.image_model_id)
            journal.emit('run_completed')
        except Exception as exc:
            journal.emit('run_failed', journal.current_agent, **error_details(exc), message=public_error(exc))
        finally:
            self._release()

    def _image(self, campaign, journal, product, changes='', base_image=None,
               revision_reference=None, model_id=None):
        return self.images.execute(campaign, journal, product, changes, base_image,
                                   revision_reference, model_id=model_id)

    def image(self, run_id, request=None):
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
        self._claim()
        try:
            journal = self.repository.resume(run_id)
            product = self.repository.product(run_id)
            self.active_id = run_id

            def work():
                try:
                    revision = self.repository.save_revision(journal, reference) if reference else None
                    self._image(campaign, journal, product, request.changes.strip(), base_image,
                                revision, model_id=request.image_model_id)
                    journal.emit('run_completed')
                except Exception as exc:
                    journal.emit('run_failed', journal.current_agent, **error_details(exc), message=public_error(exc))
                finally:
                    self._release()

            self.scheduler.submit(work)
        except BaseException:
            self._release()
            raise

    def close(self, timeout=None):
        return self.scheduler.close(timeout)
