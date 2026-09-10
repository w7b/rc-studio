import json
from realcenter_marketing.infrastructure.system_catalog import SystemCatalog, usage_audit, system_activity


def test_catalog_rebuild_change_removal_cache_and_secret_exclusion(tmp_path):
    root = tmp_path/'project'
    src = root/'src'; src.mkdir(parents=True)
    (src/'a.py').write_text('def hello():\n    return 1\n')
    (root/'.env').write_text('SECRET=do-not-index')
    catalog = SystemCatalog(root); catalog.rebuild()
    assert catalog.state['status']=='ready'
    assert catalog.snapshot()['input_tokens']==0
    assert '.env' not in json.dumps(catalog.snapshot())
    catalog.rebuild(); assert catalog.state['changed'] is False
    (src/'b.py').write_text('def second():\n    return 2\n')
    catalog.rebuild(); assert catalog.state['changed'] is True
    (src/'b.py').unlink(); catalog.rebuild()
    assert catalog.snapshot()['history'][-1]['removed']==['project/src/b.py']
    assert not any('second' in n.get('label','') for n in catalog.snapshot()['graph']['nodes'])


def test_usage_includes_assists_and_activity_redacts(tmp_path):
    for folder in ('runs/run-'+'a'*32, 'brief-assists/test'):
        d=tmp_path/'campaigns'/folder; d.mkdir(parents=True)
        (d/'usage.json').write_text(json.dumps({'text':{'model':'test','by_agent':{'Director':{'requests':1,'input_tokens':10,'output_tokens':2}}}}))
        (d/'events.jsonl').write_text(json.dumps({'event':'response_received','time':'2026-09-10','secret':'hidden'})+'\n{partial')
    result=usage_audit(tmp_path)
    assert result['input_tokens']==20 and result['output_tokens']==4
    assert result['record_count']==2
    assert 'hidden' not in json.dumps(system_activity(tmp_path))
