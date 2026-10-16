"""Admissão, execução e revisão de campanhas."""
import base64
import pytest
from queue_fake import FakeJobQueue
from studio_ai.application.commands import RunRequest
from studio_ai.application.errors import BusyError
from studio_ai.bootstrap.services import CampaignService
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from studio_ai.application.commands import RunRequest, ReferenceRequest
from studio_ai.infrastructure.persistence.campaign_repository import FileCampaignRepository
from studio_ai.infrastructure.persistence.filesystem import media_catalog
from studio_ai.infrastructure.references import save_reference
from studio_ai.presentation.http.server import make_server
from test_references import picture
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from studio_ai.application.commands import AssistRequest, RunRequest
from studio_ai.application.identity.quota import QuotaError, UsageQuota, limits_for
from studio_ai.infrastructure.identity.memory_quotas import MemoryQuotaLedger
from studio_ai.infrastructure.execution import LocalExecutionScheduler
from studio_ai.infrastructure.process_lease import ProcessLease
from studio_ai.application.commands import ImageRequest
import asyncio
import io
from PIL import Image
from studio_ai.infrastructure.image_generation import generate_feed
from studio_ai.bootstrap.services import CampaignService, ImageRequest
from studio_ai.bootstrap.campaigns import create_campaign
from studio_ai.domain.campaigns import CampaignBrief
from openai import BadRequestError
from studio_ai.application.diagnostics import error_details
from studio_ai.application.errors import ImageRequestLimitError, public_error
from studio_ai.infrastructure.image_prompt import fit_image_prompt


# ---- campaign_dispatch -------------------------------------------------------

def test_admission_enqueues_without_execution_and_resume_finishes(root):
    service = CampaignService(root)
    service.queue = queue = FakeJobQueue()
    request = RunRequest(request='Campanha de teste', mode='demo',
                         upload=base64.b64encode((root / 'brand/references/fixture.png').read_bytes()).decode(),
                         reference_upload=base64.b64encode((root / 'brand/references/fixture.png').read_bytes()).decode())
    try:
        run_id = service.start(request)
        assert len(queue.jobs) == 1
        job = queue.jobs[0]
        assert job['payload']['request']['upload'] is None
        assert job['payload']['request']['reference_upload'] is None
        assert service.repository.last_event(run_id) == 'run_queued'
        assert not service.repository.has_campaign(run_id)
        assert not service.busy
        with pytest.raises(BusyError):
            service.retry(run_id)
        service.queue = None
        service.resume(job['kind'], run_id, job['payload'])
        assert service.repository.last_event(run_id) == 'run_completed'
        assert service.repository.has_campaign(run_id)
    finally:
        service.close()


def test_resume_propagates_real_execution_failure(root):
    service = CampaignService(root)
    service.queue = queue = FakeJobQueue()
    async def fail(*args):
        raise RuntimeError('provider exploded')
    try:
        run_id = service.start(RunRequest(request='Campanha de teste', mode='demo'))
        service.execute = fail
        service.queue = None
        with pytest.raises(RuntimeError, match='provider exploded'):
            service.resume('campaign', run_id, queue.jobs[0]['payload'])
        assert service.repository.last_event(run_id) == 'run_failed'
        assert not service.busy
    finally:
        service.close()


def test_missing_run_reports_mount_problem_without_creating_directory(root):
    service = CampaignService(root)
    try:
        with pytest.raises(ValueError, match='diretório.*montagem'):
            service.resume('campaign', 'run-' + 'a' * 32,
                           {'request': {'request': 'teste', 'mode': 'demo'}})
        assert not service.busy
    finally:
        service.close()


def test_worker_may_complete_before_enqueue_returns(root):
    web, background = CampaignService(root), CampaignService(root)
    class ImmediateQueue(FakeJobQueue):
        def enqueue(self, kind, payload, run_id):
            result = super().enqueue(kind, payload, run_id)
            background.resume(kind, run_id, payload)
            self.jobs[-1]['status'] = 'done'
            return result
    web.queue = ImmediateQueue()
    try:
        run_id = web.start(RunRequest(request='Teste rápido', mode='demo'))
        assert web.repository.last_event(run_id) == 'run_completed'
        assert not web.busy
    finally:
        web.close()
        background.close()


def test_enqueue_failure_refunds_only_web_reservation_and_releases_slot(root):
    from studio_ai.application.identity.quota import UsageQuota
    from studio_ai.infrastructure.identity.memory_quotas import MemoryQuotaLedger
    ledger = MemoryQuotaLedger()
    service = CampaignService(root, quota=UsageQuota(ledger, 1, 'DEFAULT', lambda: '2026-09'))
    service.validate_live = lambda *args: None
    class UnavailableQueue(FakeJobQueue):
        def enqueue(self, *args):
            raise OSError('database unavailable')
    service.queue = UnavailableQueue()
    try:
        with pytest.raises(OSError, match='database unavailable'):
            service.start(RunRequest(request='Campanha live'))
        assert not service.busy
        assert ledger.used(1, '2026-09').get('campaigns', 0) == 0
        run_id = next((root / 'campaigns/runs').iterdir()).name
        assert service.repository.last_event(run_id) == 'run_failed'
    finally:
        service.close()


def test_worker_failure_keeps_reservation_as_an_audit_record(root):
    from studio_ai.application.identity.quota import UsageQuota
    from studio_ai.infrastructure.identity.memory_quotas import MemoryQuotaLedger
    ledger = MemoryQuotaLedger()
    web = CampaignService(root, quota=UsageQuota(ledger, 1, 'DEFAULT', lambda: '2026-09'))
    worker = CampaignService(root)
    web.queue = queue = FakeJobQueue()
    web.validate_live = lambda *args: None
    async def fail(*args):
        raise RuntimeError('provider failure')
    worker.execute = fail
    try:
        run_id = web.start(RunRequest(request='Campanha live'))
        payload = queue.jobs[0]['payload']
        assert payload['reservation'] == {'tenant_id': 1, 'period': '2026-09', 'amounts': {'campaigns': 1}}
        with pytest.raises(RuntimeError):
            worker.resume('campaign', run_id, payload)
        assert ledger.used(1, '2026-09')['campaigns'] == 1
    finally:
        web.close()
        worker.close()


def test_image_revision_materializes_inputs_before_enqueue_and_rehydrates(root):
    from studio_ai.application.commands import ImageRequest
    from studio_ai.infrastructure.persistence.filesystem import media_catalog
    web, worker = CampaignService(root), CampaignService(root)
    try:
        admission = web.admit(RunRequest(request='Base da revisão', mode='demo'))
        web.run(admission)
        run_id = admission.run_id
        campaign = web.repository.campaign(run_id).model_copy(update={'execution_mode': 'live'})
        admission.journal.save('campaign', campaign)
        picture = (root / 'brand/references/fixture.png').read_bytes()
        image_path = admission.journal.directory / 'feed-original.png'
        image_path.write_bytes(picture)
        image_id = next(key for key, value in media_catalog(root).items() if value['path'] == image_path)
        web.queue = queue = FakeJobQueue()
        web.validate_live = lambda *args: None
        request = ImageRequest(changes='Mais contraste', base_image_id=image_id,
                               reference_upload=base64.b64encode(picture).decode())
        assert web.image(run_id, request) == run_id
        payload = queue.jobs[0]['payload']
        assert payload['request']['reference_upload'] is None
        assert payload['base_image'] == 'feed-original.png'
        assert payload['revision_reference'].startswith('revision-inputs/')
        revision = admission.journal.directory / payload['revision_reference']
        assert revision.read_bytes() == picture
        calls = []
        def generate(campaign, journal, product, changes, base, reference, **kwargs):
            calls.append((changes, base.read_bytes(), reference.read_bytes()))
        worker.images.execute = generate
        worker.resume('image', run_id, payload)
        assert calls == [('Mais contraste', picture, picture)]
        assert web.repository.last_event(run_id) == 'run_completed'
    finally:
        web.close()
        worker.close()


# ---- campaign_inputs ---------------------------------------------------------

@pytest.fixture
def http_studio(isolated_root):
    server = make_server(isolated_root, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    token = json.load(urlopen(base + '/api/config'))['token']

    def call(path, payload=None):
        request = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                          headers={'Content-Type': 'application/json', 'X-App-Token': token})
        with urlopen(request, timeout=15) as response:
            return response.status, json.load(response)

    try:
        yield call
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.parametrize('reference', [False, True])
@pytest.mark.parametrize('product', [False, True])
def test_demo_http_campaign_with_library_inputs(http_studio, isolated_root, reference, product):
    payload = {'request': 'Campanha pelo formulário', 'mode': 'demo', 'generate_image': False}
    content = picture()
    for enabled, kind, field in [(reference, 'feed', 'reference_id'), (product, 'product', 'product_id')]:
        if enabled:
            status, item = http_studio('/api/references', {
                'kind': kind, 'title': 'Imagem de teste', 'upload': base64.b64encode(content).decode()})
            assert status == 201
            assert item in http_studio('/api/references')[1]
            payload[field] = item['id']
    status, started = http_studio('/api/runs', payload)
    assert status == 202
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run = next(item for item in http_studio('/api/runs')[1]['runs'] if item['id'] == started['id'])
        if run['status'] in ('completed', 'failed'):
            break
        time.sleep(.02)
    assert run['status'] == 'completed'
    assert run['outputs']['campaign']['delegation_log'] == ['social_media', 'copywriter', 'creative']
    assert run['usage']['text']['total_tokens'] == 0
    directory = isolated_root / 'campaigns/runs' / started['id']
    for present, name in [(reference, 'reference'), (product, 'product')]:
        path = directory / f'{name}.png'
        assert path.exists() is present
        if present:
            assert path.read_bytes() == content
    assert (directory / 'legenda-feed.txt').is_file()


def test_reference_id_resolves_same_bytes_as_upload(isolated_root):
    encoded = base64.b64encode(picture()).decode()
    item = save_reference(isolated_root, ReferenceRequest(kind='feed', upload=encoded))
    repository = FileCampaignRepository(isolated_root)
    assert repository.prepare_inputs(RunRequest(request='Teste', reference_id=item['id'])) == (
        repository.prepare_inputs(RunRequest(request='Teste', reference_upload=encoded)))


def test_legacy_media_id_remains_usable_as_reference(isolated_root):
    save_reference(isolated_root, ReferenceRequest(kind='product', upload=base64.b64encode(picture()).decode()))
    key = next(iter(media_catalog(isolated_root)))
    assert FileCampaignRepository(isolated_root).prepare_inputs(RunRequest(request='Teste', reference_id=key))[1] == picture()


def test_unknown_reference_is_clear_and_does_not_start_run(http_studio, isolated_root):
    with pytest.raises(HTTPError) as error:
        http_studio('/api/runs', {'request': 'Teste', 'mode': 'demo', 'reference_id': 'inexistente'})
    assert error.value.code == 400
    assert 'referência válida' in json.load(error.value)['error']
    assert not list((isolated_root / 'campaigns/runs').glob('run-*'))


@pytest.mark.parametrize('valid_id', [False, True])
def test_reference_upload_takes_precedence_even_over_invalid_id(isolated_root, valid_id):
    key = 'inexistente'
    if valid_id:
        import io
        from PIL import Image
        other = io.BytesIO()
        Image.new('RGB', (20, 20), 'blue').save(other, format='PNG')
        key = save_reference(isolated_root, ReferenceRequest(
            kind='feed', upload=base64.b64encode(other.getvalue()).decode()))['id']
    request = RunRequest(request='Teste', reference_upload=base64.b64encode(picture()).decode(),
                         reference_id=key)
    assert FileCampaignRepository(isolated_root).prepare_inputs(request)[1] == picture()


def test_library_ids_do_not_cross_tenants(isolated_root, tmp_path):
    item = save_reference(tmp_path / 'other', ReferenceRequest(kind='feed', upload=base64.b64encode(picture()).decode()))
    with pytest.raises(ValueError, match='referência válida'):
        FileCampaignRepository(isolated_root).prepare_inputs(RunRequest(request='Teste', reference_id=item['id']))


def test_visual_reference_cannot_be_used_as_product(isolated_root):
    item = save_reference(isolated_root, ReferenceRequest(kind='feed', upload=base64.b64encode(picture()).decode()))
    with pytest.raises(ValueError, match='foto válida'):
        FileCampaignRepository(isolated_root).prepare_inputs(RunRequest(request='Teste', product_id=item['id']))


# ---- busy_state --------------------------------------------------------------

@pytest.mark.parametrize('operation', ['assist', 'campaign', 'image'])
def test_busy_rejection_does_not_consume_quota(tmp_path, operation):
    ledger = MemoryQuotaLedger()
    service = CampaignService(tmp_path, quota=UsageQuota(ledger, 1, 'DEFAULT', lambda: '2026-09'))
    service.validate_live = lambda *args: None
    service.lock.acquire()
    try:
        with pytest.raises(BusyError):
            if operation == 'assist':
                service.assist(AssistRequest(request='Ideia'))
            elif operation == 'campaign':
                service.start(RunRequest(request='Ideia'))
            else:
                service.repository.campaign = lambda _: SimpleNamespace(execution_mode='live')
                service.image('run-example')
        assert not any(ledger.used(1, '2026-09').values())
    finally:
        service.lock.release()
        service.close()


def test_http_reports_briefing_busy_until_provider_finishes(isolated_root, monkeypatch):
    from studio_ai.presentation.http.server import make_server
    entered, release = threading.Event(), threading.Event()
    async def improve(*args, **kwargs):
        entered.set()
        release.wait(10)
        raise RuntimeError('provider failed')
    monkeypatch.setattr('studio_ai.bootstrap.settings.Settings.validate_live', lambda self: None)
    monkeypatch.setattr('studio_ai.bootstrap.services.improve_brief', improve)
    server = make_server(isolated_root, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def get(path):
        with urlopen(base + path) as response:
            return json.load(response)
    pool = ThreadPoolExecutor(1)
    try:
        token = get('/api/config')['token']
        request = Request(base + '/api/brief-assist', data=json.dumps({'request': 'Ideia'}).encode(),
                          headers={'Content-Type': 'application/json', 'X-App-Token': token})
        future = pool.submit(urlopen, request)
        assert entered.wait(5)
        state = get('/api/runs')
        assert state['active_id'] is None
        assert state['busy'] is True
        release.set()
        with pytest.raises(HTTPError):
            future.result(5)
        assert get('/api/runs')['busy'] is False
    finally:
        release.set()
        pool.shutdown()
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.parametrize('operation,metric', [('assist', 'assists'), ('campaign', 'campaigns')])
def test_quota_rejection_releases_execution_slot(tmp_path, operation, metric):
    allowance = UsageQuota(MemoryQuotaLedger(), 1, 'DEFAULT', lambda: '2026-09')
    allowance.reserve(**{metric: limits_for('DEFAULT')[metric]})
    service = CampaignService(tmp_path, quota=allowance)
    service.validate_live = lambda *args: None
    try:
        with pytest.raises(QuotaError):
            if operation == 'assist':
                service.assist(AssistRequest(request='Ideia'))
            else:
                service.start(RunRequest(request='Ideia'))
        assert service.busy is False
    finally:
        service.close()


# ---- execution ---------------------------------------------------------------

def test_close_waits_for_work_and_rejects_new_submissions():
    scheduler = LocalExecutionScheduler()
    started, gate = threading.Event(), threading.Event()
    assert scheduler.acquire()
    def work():
        started.set()
        gate.wait(3)
        scheduler.release()
    scheduler.submit(work)
    # Submitting now means "queued"; close only owes a wait to work already in flight.
    assert started.wait(3)
    try:
        assert not scheduler.close(timeout=.01)
        assert not scheduler.acquire()
    finally:
        gate.set()
        assert scheduler.close(timeout=3)
    assert not scheduler.acquire()


def test_only_one_process_lease_per_data_root_and_release(tmp_path):
    first = ProcessLease(tmp_path).acquire()
    try:
        with pytest.raises(RuntimeError, match='processo'):
            ProcessLease(tmp_path).acquire()
        # Independent data roots may run in parallel.
        other = ProcessLease(tmp_path / 'other').acquire()
        other.close()
    finally:
        first.close()
    again = ProcessLease(tmp_path).acquire()
    again.close()


def test_failed_image_setup_releases_execution_slot(settings, demo, root, tmp_path, monkeypatch):
    import asyncio
    from studio_ai.bootstrap.campaigns import create_campaign
    from studio_ai.domain.campaigns import CampaignBrief
    from studio_ai.infrastructure.observability.journal import RunJournal
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Teste'), settings, model=demo))
    campaign.execution_mode = 'live'
    run_id = 'run-' + 'e' * 32
    journal = RunJournal(root / 'campaigns/runs' / run_id)
    journal.save('campaign', campaign)
    service = CampaignService(root)
    monkeypatch.setattr(service, 'validate_live', lambda *_: None)
    def unavailable(*args):
        raise OSError('unavailable')
    monkeypatch.setattr(service.repository, 'resume', unavailable)
    with pytest.raises(OSError):
        service.image(run_id, ImageRequest())
    assert service.active_id is None
    assert service.lock.acquire(blocking=False)
    service.lock.release()


def test_closed_service_cannot_start_more_work(root):
    from studio_ai.application.commands import RunRequest
    service = CampaignService(root)
    assert service.close(timeout=0)
    with pytest.raises(BusyError):
        service.start(RunRequest(request='Teste', mode='demo'))


def test_each_tenant_owns_its_slot_so_one_store_cannot_stack_two_runs():
    from studio_ai.infrastructure.execution import ExecutionPool
    pool = ExecutionPool(capacity=2)
    loja_a, loja_b = pool.scheduler('loja-a'), pool.scheduler('loja-b')
    try:
        assert loja_a.acquire()
        # The same store asking twice is the case that must keep answering BusyError.
        assert not loja_a.acquire()
        # A different store is unaffected by its neighbour.
        assert loja_b.acquire()
    finally:
        loja_a.release()
        loja_b.release()
        pool.close(timeout=3)


def test_work_beyond_capacity_waits_in_line_with_a_visible_position():
    from studio_ai.infrastructure.execution import ExecutionPool
    pool = ExecutionPool(capacity=1)
    loja_a, loja_b = pool.scheduler('loja-a'), pool.scheduler('loja-b')
    started, hold, ran_b = threading.Event(), threading.Event(), threading.Event()
    try:
        assert loja_a.acquire()
        def first():
            started.set()
            hold.wait(3)
            loja_a.release()
        loja_a.submit(first)
        assert started.wait(3)

        assert loja_b.acquire()
        def second():
            ran_b.set()
            loja_b.release()
        loja_b.submit(second)

        # The only worker is busy with loja-a, so loja-b is queued, not rejected.
        assert loja_b.position() == 1
        assert not ran_b.wait(.2)

        hold.set()
        assert ran_b.wait(3)
        assert loja_b.position() is None
    finally:
        hold.set()
        pool.close(timeout=3)


def test_close_discards_work_that_never_started():
    """A queued run has spent nothing, so shutdown drops it and hands its slot back
    instead of blocking on a queue that could outlast the stop grace period."""
    from studio_ai.infrastructure.execution import ExecutionPool
    pool = ExecutionPool(capacity=1)
    loja_a, loja_b = pool.scheduler('loja-a'), pool.scheduler('loja-b')
    started, hold, ran_b = threading.Event(), threading.Event(), threading.Event()
    outcome = []
    try:
        assert loja_a.acquire()
        def first():
            started.set()
            hold.wait(5)
            loja_a.release()
        loja_a.submit(first)
        assert started.wait(3)

        # loja-b is queued behind the only worker, which is still inside first().
        assert loja_b.acquire()
        loja_b.submit(lambda: (ran_b.set(), loja_b.release()))
        assert loja_b.position() == 1

        closer = threading.Thread(target=lambda: outcome.append(pool.close(timeout=5)))
        closer.start()
        hold.set()
        closer.join(8)

        assert outcome == [True]
        assert not ran_b.is_set()
        # The discarded run gave its slot back rather than leaving the store locked out.
        assert not loja_b.lock.locked()
        assert not pool.scheduler('loja-c').acquire()
    finally:
        hold.set()


# ---- image_revision ----------------------------------------------------------

def test_revision_passes_base_and_changes_and_preserves_original(settings, demo, tmp_path):
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    data=io.BytesIO()
    Image.new('RGB',(1152,1440),'red').save(data,'PNG')
    original=tmp_path/'feed-original.png'
    original.write_bytes(data.getvalue())
    reference=tmp_path/'demonstracao.png'
    reference.write_bytes(data.getvalue())
    captured={}
    def edit(**kwargs):
        captured.update(kwargs)
        captured['names']=[image.name for image in kwargs['image']]
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(data.getvalue()).decode())])
    result=generate_feed(campaign,settings,tmp_path,client=SimpleNamespace(images=SimpleNamespace(edit=edit)),changes='Troque o fundo para azul',base_image=original,revision_reference=reference)
    assert captured['names'][0]==str(original)
    assert 'Troque o fundo para azul' in captured['prompt']
    assert original.read_bytes()==data.getvalue()
    assert result != original
    assert result.with_suffix('.json').is_file()
    assert str(reference) in captured['names']
    assert 'Demonstração enviada para ESTA revisão' in captured['prompt']
    import json
    assert {'source':'revision_upload','file':'demonstracao.png'} in json.loads(result.with_suffix('.json').read_text(encoding='utf-8'))['references']


def test_revision_requires_image_from_same_run(tmp_path):
    service=CampaignService(tmp_path)
    with pytest.raises(ValueError,match='Selecione uma arte'):
        service.image('run-'+'a'*32,ImageRequest(base_image_id='unknown',changes='Mude a cor'))
    with pytest.raises(ValueError,match='imagem base'):
        service.image('run-'+'a'*32,ImageRequest(changes='Mude a cor'))


def test_revision_upload_is_scoped_to_one_request_and_keeps_original(settings, demo, tmp_path, monkeypatch):
    import time
    from studio_ai.infrastructure.observability.journal import RunJournal
    from studio_ai.infrastructure.persistence.filesystem import media_catalog
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    campaign.execution_mode = 'live'
    run_id = 'run-'+'b'*32
    directory = tmp_path/'campaigns/runs'/run_id
    journal=RunJournal(directory); journal.save('campaign', campaign)
    data=io.BytesIO(); Image.new('RGB',(8,8),'blue').save(data,'PNG')
    (directory/'feed-original.png').write_bytes(data.getvalue())
    (directory/'reference.png').write_bytes(data.getvalue())
    base=next(m['id'] for m in media_catalog(tmp_path).values() if m['name']=='feed-original.png')
    service=CampaignService(tmp_path)
    calls=[]
    def fake(*args, **kwargs):
        calls.append(args[-1])
        if args[-1]: assert args[-1].read_bytes()==data.getvalue()
    monkeypatch.setattr(service,'_image',fake)
    monkeypatch.setattr('studio_ai.bootstrap.settings.Settings.validate_live',lambda self: None)
    for upload in (base64.b64encode(data.getvalue()).decode(), None):
        service.image(run_id,ImageRequest(base_image_id=base,changes='Mude o fundo',reference_upload=upload))
        deadline=time.monotonic()+5
        while service.active_id and time.monotonic()<deadline: time.sleep(.01)
        assert service.active_id is None
    assert calls[0].parent==directory/'revision-inputs'
    assert calls[1] is None
    assert (directory/'reference.png').read_bytes()==data.getvalue()
    assert (directory/'feed-original.png').read_bytes()==data.getvalue()


def test_revision_rejects_invalid_demo_upload_before_running(tmp_path):
    service=CampaignService(tmp_path)
    with pytest.raises(ValueError):
        service.image('run-'+'a'*32,ImageRequest(reference_upload=base64.b64encode(b'not an image').decode()))
    assert service.active_id is None


# ---- image_request_limits ----------------------------------------------------

def test_small_prompt_keeps_complete_brand():
    brand = {'brand.md': '# Marca\n\nDireção.', 'colors.md': '# Cores\n\nAzul.'}
    prompt, compacted = fit_image_prompt('Fatos exatos.', brand, ['Logo'])
    assert not compacted
    assert '\n'.join(brand.values()) in prompt
    assert prompt.startswith('Fatos exatos.')
    assert json.loads(prompt.split('Imagens de entrada, em ordem: ')[1]) == ['Logo']


def test_large_brand_keeps_all_guides_facts_revision_and_whole_paragraphs():
    brand = {name: f'# {name}\n\nRegra essencial {name}.\n\n' + '\n\n'.join(
        f'Parágrafo {i}: ' + 'exemplo ' * 100 + 'FIM.' for i in range(40))
        for name in ('brand', 'colors', 'typography', 'visual')}
    fixed = 'Produto exato, preço R$ 1,89. REVISÃO: preservar o rótulo.'
    prompt, compacted = fit_image_prompt(fixed, brand, ['Imagem base', 'Produto', 'Logo'])
    assert compacted and len(prompt) <= 32_000
    assert prompt.startswith(fixed)
    assert all(f'Regra essencial {name}.' in prompt for name in brand)
    brand_text = prompt.split('\nImagens de entrada, em ordem: ')[0]
    assert all(block.endswith('FIM.') for block in brand_text.split('\n\n') if block.startswith('Parágrafo'))
    assert json.loads(prompt.split('Imagens de entrada, em ordem: ')[1]) == ['Imagem base', 'Produto', 'Logo']


def test_essential_prompt_over_limit_is_not_truncated():
    with pytest.raises(ImageRequestLimitError) as caught:
        fit_image_prompt('fato ' * 7_000, {'brand': 'Preservar logo.'}, [])
    assert caught.value.param == 'prompt'
    assert 'instruções essenciais' in public_error(caught.value)


def test_exact_character_boundary_and_empty_brand():
    overhead = len(fit_image_prompt('', {}, [])[0])
    assert len(fit_image_prompt('x' * (32_000 - overhead), {}, [])[0]) == 32_000
    with pytest.raises(ImageRequestLimitError):
        fit_image_prompt('x' * (32_001 - overhead), {}, [])


def test_adapter_sends_bounded_request_and_saves_diagnostics(settings, demo, tmp_path):
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    (settings.project_root / 'brand/visual-guidelines.md').write_text(
        '# Diretrizes\n\nPreservar produto.\n\n' + '\n\n'.join('Exemplo. ' * 200 for _ in range(40)), encoding='utf-8')
    captured = {}
    class Captured(Exception):
        pass
    def edit(**kwargs):
        captured.update(kwargs)
        raise Captured()
    with pytest.raises(Captured):
        generate_feed(campaign, settings, tmp_path, client=SimpleNamespace(images=SimpleNamespace(edit=edit)),
                      changes='Manter título e trocar o fundo.', base_image=settings.project_root / 'brand/references/fixture.png')
    assert len(captured['prompt']) <= 32_000
    assert campaign.copywriting.headline in captured['prompt']
    assert campaign.creative.visual_direction in captured['prompt']
    assert 'Manter título e trocar o fundo.' in captured['prompt']
    metadata = json.loads((tmp_path / 'image-request.json').read_text())
    assert metadata['brand_compacted'] is True
    assert metadata['prompt_characters'] == len(captured['prompt'])


def test_excess_references_rejected_before_provider_call(settings, demo, tmp_path):
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Campanha'), settings, model=demo))
    directory = settings.project_root / 'brand/references'
    for i in range(16):
        (directory / f'extra-{i}.png').write_bytes((directory / 'fixture.png').read_bytes())
    # Only declared references are attached, so the extras join the same family.
    declared = {'fixture.png': 'produto', **{f'extra-{i}.png': 'produto' for i in range(16)}}
    (directory / 'families.json').write_text(json.dumps({'files': declared}), encoding='utf-8')
    with pytest.raises(ImageRequestLimitError) as caught:
        generate_feed(campaign, settings, tmp_path, client=SimpleNamespace())
    assert error_details(caught.value)['request_limit'] == {'param': 'image', 'actual': 17, 'limit': 16}


@pytest.mark.parametrize('nested', [False, True])
def test_provider_diagnostics_keep_identifiers_without_private_payload(nested):
    body = {'param': 'prompt', 'code': 'string_above_max_length', 'type': 'invalid_request_error',
            'message': 'private prompt sk-secret', 'input': 'private customer data'}
    exc = BadRequestError('private error', response=SimpleNamespace(status_code=400, request=SimpleNamespace(), headers={}),
                          body={'error': body} if nested else body)
    details = error_details(exc)
    assert details['provider_error'] == {key: body[key] for key in ('param', 'code', 'type')}
    assert 'private' not in json.dumps(details) and 'sk-secret' not in json.dumps(details)
    body['param'], body['code'] = 'private_prompt', 'sk-secret'
    assert error_details(exc)['provider_error'] == {'type': 'invalid_request_error'}
