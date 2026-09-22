"""Operational logs read straight from the run journals.

This replaces the Graphify AST catalog that used to live here. That catalog described the
product's own source code, which is of no use to a store and was a liability to serve: it
was a public route that indexed tenant data roots. What an operator actually needs is what
happened — runs, failures, token spend — so that is all this module produces now.
"""
import json
from pathlib import Path


def read_json(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {} if fallback is None else fallback


def system_activity(root):
    events = []
    paths = list((root / 'campaigns' / 'runs').glob('run-*/events.jsonl'))
    paths += list((root / 'campaigns' / 'brief-assists').glob('*/events.jsonl'))
    paths += list((root / 'consultations').glob('*/events.jsonl'))
    for path in paths:
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            events.append({'run_id': path.parent.name, **{k: event[k] for k in
                ('time', 'event', 'agent', 'input_tokens', 'output_tokens', 'error_type', 'card') if k in event}})
    return sorted(events, key=lambda e: e.get('time', ''), reverse=True)[:250]


def usage_audit(root):
    groups = {}
    records = []
    paths = list((root / 'campaigns' / 'runs').glob('run-*/usage.json'))
    paths += list((root / 'campaigns' / 'brief-assists').glob('*/usage.json'))
    paths += list((root / 'consultations').glob('*/usage.json'))
    for path in paths:
        usage = read_json(path, {})
        model = usage.get('text', {}).get('model', 'unknown')
        records.append({'id': path.parent.name, 'kind': 'consultation' if path.parent.parent.name == 'consultations' else 'brief-assist' if path.parent.parent.name == 'brief-assists' else 'campaign',
                        'text': usage.get('text', {}), 'image': usage.get('image', {})})
        for name, item in usage.get('text', {}).get('by_agent', {}).items():
            key = (name, model)
            bucket = groups.setdefault(key, {'agent': name, 'model': model, 'requests': 0, 'input_tokens': 0,
                'output_tokens': 0, 'cached_input_tokens': 0, 'cache_write_input_tokens': 0})
            for field in ('requests', 'input_tokens', 'output_tokens', 'cached_input_tokens', 'cache_write_input_tokens'):
                bucket[field] += int(item.get(field, 0) or 0)
    rows = sorted(groups.values(), key=lambda r: r['input_tokens'], reverse=True)
    events = system_activity(root)
    return {'agents': rows, 'records': records, 'record_count': len(records),
            'input_tokens': sum(r['input_tokens'] for r in rows), 'output_tokens': sum(r['output_tokens'] for r in rows),
            'recent_repairs': sum(e['event'] == 'repair_started' for e in events),
            'notes': ['O Director normalmente faz quatro chamadas: três delegações e a revisão final.',
                      'Especialistas: uma chamada por entrega; correção de schema pode exigir uma tentativa adicional.',
                      'Removida a cópia duplicada das entregas do system prompt do Director; resultados integrais permanecem no histórico.',
                      'Modelos, revisão final e contexto factual dos especialistas foram mantidos.',
                      'Sem comparação live antes/depois, não há percentual de economia ou equivalência editorial comprovado.']}
