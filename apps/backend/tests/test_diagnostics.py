import asyncio
import json

import pytest
from agents import ModelBehaviorError

from realcenter_marketing.application.diagnostics import report
from realcenter_marketing.infrastructure.observability.journal import RunJournal
from realcenter_marketing.domain.campaigns import CampaignBrief
from realcenter_marketing.bootstrap.campaigns import create_campaign


def test_failed_specialist_repairs_once_without_repeating_previous_agents(settings, demo, tmp_path):
    original = demo.get_response
    attempts = []
    async def respond(*args, **kwargs):
        schema = kwargs['output_schema'].output_type.__name__
        attempts.append(schema)
        response = await original(*args, **kwargs)
        if schema == 'CopyPack' and attempts.count('CopyPack') == 1:
            value = json.loads(response.output[0].content[0].text)
            value['stories'] = []
            response.output[0].content[0].text = json.dumps(value)
        return response
    demo.get_response = respond
    journal = RunJournal(tmp_path / 'run')
    campaign = asyncio.run(create_campaign(CampaignBrief(request='Teste'), settings, model=demo, journal=journal))
    assert campaign.copywriting.feed_caption
    assert attempts.count('CopyPack') == 2
    assert attempts.count('SocialPlan') == 1
    assert attempts.count('CreativeBrief') == 1
    events = [json.loads(line) for line in (journal.directory / 'events.jsonl').read_text().splitlines()]
    failure = next(e for e in events if e['event'] == 'validation_failed')
    assert failure['schema'] == 'CopyPack'
    assert failure['validation_errors'][0]['location'] == ['stories']
    assert failure['validation_errors'][0]['type'] == 'too_short'
    assert sum(e['event'] == 'repair_started' for e in events) == 1
    assert any(e['event'] == 'repair_completed' for e in events)
    copy_calls = [call for call in demo.calls if call[0] == 'CopyPack']
    assert 'CORREÇÃO DE FORMATO' in json.dumps(copy_calls[1][2], ensure_ascii=False)
    assert report('run', events, None, {})['recovered']


def test_repair_stops_after_one_extra_call_and_does_not_log_content(settings, demo, tmp_path):
    demo.responses['CopyPack']['stories'] = []
    demo.responses['CopyPack']['headline'] = 'PRIVATE-OUTPUT-MARKER'
    journal = RunJournal(tmp_path / 'run')
    with pytest.raises(ModelBehaviorError):
        asyncio.run(create_campaign(CampaignBrief(request='Teste'), settings, model=demo, journal=journal))
    assert len([call for call in demo.calls if call[0] == 'CopyPack']) == 2
    logs = (journal.directory / 'events.jsonl').read_text()
    assert 'repair_exhausted' in logs
    assert 'PRIVATE-OUTPUT-MARKER' not in logs
    assert (journal.directory / 'social_media.json').is_file()
    assert not (journal.directory / 'copywriter.json').exists()


def test_historical_diagnostics_are_explicit_about_missing_data():
    data = report('run-old', [{'event':'run_failed','error_type':'ModelBehaviorError','agent':'Copywriter','time':'2026-09-09'}], None, {'social_media': {}})
    assert data['historical_note']
    assert not data['details_available']
    assert data['validation_errors'] == []
    assert data['saved_outputs'] == ['social_media']
    assert data['retry_scope'] == 'full_campaign'
