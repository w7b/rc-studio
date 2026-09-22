import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from identity_fake import FakeIdentityStore
from realcenter_marketing.infrastructure.admin_metrics import collect_metrics
from realcenter_marketing.infrastructure.observability.journal import RunJournal


def journal(root, name, date, *, assist=False, entries=None, unknown=False):
    path = root / 'campaigns' / ('brief-assists' if assist else 'runs') / name
    path.mkdir(parents=True)
    (path / 'events.jsonl').write_text(json.dumps({'time': date, 'event': 'assist_completed' if assist else 'run_completed'}) + '\n{partial', encoding='utf-8')
    data = {'text': {'requests': 2, 'input_tokens': 100, 'output_tokens': 30, 'cost_usd': None if unknown else .2},
            'image': {'count': 1, 'cost_usd': .1}}
    if entries is not None:
        data['entries'] = entries
    (path / 'usage.json').write_text(json.dumps(data), encoding='utf-8')
    return path


def test_periods_use_all_stores_timezone_boundaries_and_unknown_cost(tmp_path):
    store = FakeIdentityStore()
    a = store.create_tenant('alpha', 'Alpha')
    b = store.create_tenant('beta', 'Beta')
    now = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store.created_stores[a.id] = now - timedelta(days=1)
    store.created_stores[b.id] = now - timedelta(days=50)
    journal(tmp_path / 'alpha', 'run-recent', '2026-09-18T12:00:00Z')
    journal(tmp_path / 'beta', 'run-month', '2026-09-02T12:00:00Z', unknown=True)
    # Sep 1 UTC is still August in Brazil.
    journal(tmp_path / 'beta', 'run-old', '2026-09-01T01:00:00Z', assist=True)
    report = collect_metrics(store, lambda slug, _: tmp_path / slug, now)
    week, month, all_time = (report['periods'][p] for p in ('week', 'month', 'all'))
    assert week['requests'] == 3 and week['new_stores'] == 1
    assert month['requests'] == 6 and month['unpriced_records'] == 1
    assert month['known_cost_usd'] == pytest.approx(.4)
    assert all_time['requests'] == 9 and all_time['new_stores'] == 2
    assert all_time['active_stores'] == 2 and all_time['brief_assists'] == 1
    assert len(report['daily']) == 30


def test_timestamped_entries_count_later_images_without_double_counting_snapshots(tmp_path):
    store = FakeIdentityStore()
    store.create_tenant('alpha', 'Alpha')
    journal(tmp_path, 'run-old', '2026-08-01T00:00:00Z', entries=[
        {'time': '2026-09-18T12:00:00Z', 'requests': 1, 'images': 1, 'known_cost_usd': .1}])
    result = collect_metrics(store, lambda *_: tmp_path, datetime(2026, 9, 19, tzinfo=timezone.utc))['periods']['week']
    assert result['campaigns'] == 0 and result['images'] == 1 and result['requests'] == 1
    assert result['known_cost_usd'] == .1 and result['legacy_records'] == 0


def test_undated_legacy_usage_only_enters_general_totals(tmp_path):
    store = FakeIdentityStore()
    store.create_tenant('alpha', 'Alpha')
    journal(tmp_path, 'run-undated', None)
    report = collect_metrics(store, lambda *_: tmp_path)
    assert report['periods']['week']['requests'] == 0
    assert report['periods']['all']['undated_records'] == 1


def test_resuming_a_legacy_journal_preserves_old_usage_once(tmp_path):
    directory = journal(tmp_path, 'run-old', '2026-09-01T12:00:00Z')
    # Use the full historical schema before resuming image generation.
    old = json.loads((directory / 'usage.json').read_text())
    old['text']['by_agent'] = {}
    (directory / 'usage.json').write_text(json.dumps(old))
    current = RunJournal.resume(directory)
    current.record_image_usage('unpriced-model')
    current.record_image_usage('unpriced-model')
    data = json.loads((directory / 'usage.json').read_text())
    assert len(data['entries']) == 3
    assert data['entries'][0]['legacy'] is True
    assert sum(row['requests'] for row in data['entries']) == 5
    assert data['entries'][-1]['unpriced_records'] == 1
