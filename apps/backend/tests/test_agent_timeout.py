import asyncio
import json
import time

import pytest

from realcenter_marketing.bootstrap.settings import Settings
from realcenter_marketing.domain.campaigns import CampaignBrief
from realcenter_marketing.infrastructure.agents_sdk.runtime import execute_campaign
from realcenter_marketing.infrastructure.observability.journal import RunJournal


def test_agent_timeout_default(settings):
    assert settings.agent_timeout_seconds == 600


def test_agent_timeout_can_be_configured(root, monkeypatch):
    monkeypatch.setenv('AGENT_TIMEOUT_SECONDS', '45')
    assert Settings.load(root).agent_timeout_seconds == 45


def test_slow_copywriter_is_cancelled_and_named_without_running_next_agent(settings, demo, tmp_path, monkeypatch):
    # A shorter test clock; production settings still enforce their minimum of 30s.
    settings = settings.model_copy(update={'agent_timeout_seconds': .5})
    original = demo.get_response
    cancelled = []

    async def slow(*args, **kwargs):
        if len(demo.calls) == 2:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
        return await original(*args, **kwargs)

    monkeypatch.setattr(demo, 'get_response', slow)
    journal = RunJournal(tmp_path / 'timeout')
    started = time.monotonic()
    with pytest.raises(TimeoutError, match=r'Copywriter.*0.5s'):
        asyncio.run(execute_campaign(CampaignBrief(request='Teste'), settings, model=demo, journal=journal))
    assert time.monotonic() - started < 4
    assert cancelled == [True]
    assert len(demo.calls) == 2
    events = [json.loads(line) for line in (journal.directory / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
    assert events[-1]['event'] == 'failed'
    assert 'Copywriter' in json.dumps(events[-1])
    assert not any(event['event'] == 'repair_started' for event in events)
