"""On-demand advice. Provider, storage and concurrency arrive as ports."""
import asyncio

from studio_ai.application.diagnostics import error_details
from studio_ai.application.errors import BusyError, public_error
from studio_ai.domain.consultations import validated_delivery


class ConsultationService:
    def __init__(self, repository, scheduler, execute, validate_live, quota=None, queue=None):
        self.repository, self.scheduler = repository, scheduler
        self.execute, self.validate_live = execute, validate_live
        self.quota, self.queue = quota, queue

    def run(self, request):
        self.validate_live(request)
        if self.queue is not None and self.queue.pending():
            raise BusyError('Já existe uma execução em andamento')
        if not self.scheduler.acquire():
            raise BusyError('Já existe uma execução em andamento')
        ticket, journal, provider_started = None, None, False
        try:
            ticket = self.quota.reserve(assists=1) if self.quota else None
            journal = self.repository.create_consultation()
            journal.save('original', request)
            journal.emit('consultation_started', role=request.role, model=request.model_id)
            def invoke():
                nonlocal provider_started
                provider_started = True
                return validated_delivery(request, asyncio.run(self.execute(request, journal)))

            result = self.scheduler.call(invoke)
            journal.save('result', result)
            journal.emit('consultation_completed', role=request.role)
            return {'id': journal.directory.name, 'role': request.role,
                    'result': result.model_dump(mode='json'),
                    'sources': [source.model_dump(mode='json') for source in request.sources],
                    'usage': self.repository.usage(journal)}
        except Exception as exc:
            if journal:
                journal.emit('consultation_failed', role=request.role, **error_details(exc), message=public_error(exc))
                raise ValueError('Não foi possível concluir a consulta. ' + public_error(exc)) from None
            raise
        finally:
            if ticket and not provider_started:
                ticket.void()
            self.scheduler.release()
