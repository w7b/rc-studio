import json
from realcenter_marketing.infrastructure.logs import usage_audit, system_activity



def test_usage_includes_assists_and_activity_redacts(tmp_path):
    for folder in ('runs/run-'+'a'*32, 'brief-assists/test'):
        d=tmp_path/'campaigns'/folder; d.mkdir(parents=True)
        (d/'usage.json').write_text(json.dumps({'text':{'model':'test','by_agent':{'Director':{'requests':1,'input_tokens':10,'output_tokens':2}}}}))
        (d/'events.jsonl').write_text(json.dumps({'event':'response_received','time':'2026-09-10','secret':'hidden'})+'\n{partial')
    result=usage_audit(tmp_path)
    assert result['input_tokens']==20 and result['output_tokens']==4
    assert result['record_count']==2
    assert 'hidden' not in json.dumps(system_activity(tmp_path))


def test_snapshot_is_memoised_until_the_run_directory_changes(root):
    """The frontend polls this every two seconds per tab. Re-reading every events.jsonl
    each time is what gives way first under load — before campaign execution does."""
    from realcenter_marketing.infrastructure.persistence import filesystem

    runs = root / 'campaigns' / 'runs' / ('run-' + 'a' * 32)
    runs.mkdir(parents=True)
    (runs / 'events.jsonl').write_text('{"event": "run_completed", "time": "2026-09-19T10:00:00"}\n',
                                       encoding='utf-8')

    reads = {'count': 0}
    original = filesystem.media_catalog

    def counting(value):
        reads['count'] += 1
        return original(value)

    filesystem.media_catalog = counting
    try:
        first = filesystem.snapshot(root)
        for _ in range(5):
            filesystem.snapshot(root)
        assert reads['count'] == 1, 'polling repetido não pode reler o disco'
        assert first[0]['status'] == 'completed'

        # A new run changes the fingerprint, so the next call rebuilds.
        (root / 'campaigns' / 'runs' / ('run-' + 'b' * 32)).mkdir()
        filesystem.snapshot(root)
        assert reads['count'] == 2
    finally:
        filesystem.media_catalog = original


def test_the_active_run_is_labelled_without_rebuilding(root):
    """active_id only decides a label, so it must not invalidate the cache."""
    from realcenter_marketing.infrastructure.persistence import filesystem

    run_id = 'run-' + 'c' * 32
    directory = root / 'campaigns' / 'runs' / run_id
    directory.mkdir(parents=True)
    (directory / 'events.jsonl').write_text('{"event": "run_started"}\n', encoding='utf-8')

    filesystem.snapshot(root)
    labelled = filesystem.snapshot(root, active_id=run_id)
    assert labelled[0]['status'] == 'running'
    assert filesystem.snapshot(root)[0]['status'] == 'interrupted'
