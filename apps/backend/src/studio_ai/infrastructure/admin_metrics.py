"""Platform metrics from tenant journals, with explicit legacy and missing-price coverage."""
import json
from datetime import datetime, timedelta, timezone

from .logs import read_json

REPORT_ZONE = timezone(timedelta(hours=-3))


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (ValueError, TypeError):
        return None


def events_from(path):
    try:
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        yield value
                except ValueError:
                    continue
    except OSError:
        return


def empty():
    return {'campaigns': 0, 'completed': 0, 'failed': 0, 'brief_assists': 0, 'consultations': 0,
            'requests': 0, 'images': 0, 'input_tokens': 0, 'output_tokens': 0,
            'cached_input_tokens': 0, 'known_cost_usd': 0.0, 'unpriced_records': 0,
            'legacy_records': 0, 'undated_records': 0, 'active_stores': 0}


def usage_record(data, at):
    text, image = data.get('text') or {}, data.get('image') or {}
    def amount(key):
        return int(text.get(key, sum(int(v.get(key, 0) or 0) for v in text.get('by_agent', {}).values())) or 0)
    image_count = int(image.get('count', 0) or 0)
    text_cost, image_cost = text.get('cost_usd'), image.get('cost_usd')
    unknown = (amount('requests') > 0 and text_cost is None) or (image_count > 0 and image_cost is None)
    return {'time': at.isoformat() if at else None, 'requests': amount('requests') + image_count,
            'images': image_count, 'input_tokens': amount('input_tokens') + int(image.get('input_tokens', 0) or 0),
            'output_tokens': amount('output_tokens') + int(image.get('output_tokens', 0) or 0),
            'cached_input_tokens': amount('cached_input_tokens'),
            'known_cost_usd': float(text_cost or 0) + float(image_cost or 0), 'unpriced_records': int(unknown)}


def collect_metrics(store, root_for, at=None):
    at = at or datetime.now(timezone.utc)
    local = at.astimezone(REPORT_ZONE)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    starts = {'week': midnight - timedelta(days=midnight.weekday()),
              'month': midnight.replace(day=1), 'all': None}
    periods = {name: {**empty(), **store.registration_counts(start, at),
                       'start': start.isoformat() if start else None, 'end': at.isoformat()}
               for name, start in starts.items()}
    activity = {name: set() for name in starts}
    daily = {(midnight - timedelta(days=i)).date().isoformat(): empty() for i in range(29, -1, -1)}

    def buckets(stamp):
        result = []
        for name, start in starts.items():
            if (stamp is None and start is None) or (stamp is not None and stamp <= at and (start is None or stamp >= start)):
                result.append((name, periods[name]))
        if stamp and stamp <= at:
            day = stamp.astimezone(REPORT_ZONE).date().isoformat()
            if day in daily:
                result.append((None, daily[day]))
        return result

    stores = store.tenants()
    for tenant in stores:
        root = root_for(tenant.slug, tenant.root_path)
        for kind, directory in (('campaigns', root / 'campaigns' / 'runs'),
                                ('brief_assists', root / 'campaigns' / 'brief-assists'),
                                ('consultations', root / 'consultations')):
            if not directory.is_dir():
                continue
            for run in directory.iterdir():
                if not run.is_dir():
                    continue
                events = list(events_from(run / 'events.jsonl'))
                dated = [value for e in events if (value := timestamp(e.get('time'))) is not None]
                started = min(dated) if dated else None
                for name, bucket in buckets(started):
                    bucket[kind] += 1
                    if name:
                        activity[name].add(tenant.id)
                terminal = next((e for e in reversed(events) if e.get('event') in
                                 ('run_completed', 'run_failed')), None)
                if terminal and kind == 'campaigns':
                    for _, bucket in buckets(timestamp(terminal.get('time'))):
                        bucket['completed' if terminal['event'] == 'run_completed' else 'failed'] += 1
                data = read_json(run / 'usage.json')
                if not data:
                    continue
                entries = data.get('entries')
                legacy = entries is None
                entries = entries if entries is not None else [usage_record(data, started)]
                for entry in entries:
                    stamp = timestamp(entry.get('time'))
                    for name, bucket in buckets(stamp):
                        for key in ('requests', 'images', 'input_tokens', 'output_tokens',
                                    'cached_input_tokens', 'known_cost_usd', 'unpriced_records'):
                            bucket[key] += entry.get(key, 0) or 0
                        bucket['legacy_records'] += int(legacy or entry.get('legacy', False))
                        bucket['undated_records'] += int(stamp is None)
                        if name:
                            activity[name].add(tenant.id)
    for name, bucket in periods.items():
        bucket['active_stores'] = len(activity[name])
        bucket['known_cost_usd'] = round(bucket['known_cost_usd'], 6)
    return {'periods': periods, 'daily': [{'date': day, **values} for day, values in daily.items()],
            'stores': len(stores), 'suspended_stores': sum(not t.active for t in stores),
            'generated_at': at.isoformat(), 'timezone': 'UTC−03:00', 'currency': 'USD',
            'notes': ['Semana começa na segunda-feira; mês começa no dia 1, em UTC−03:00.',
                      'Novos clientes = novas lojas; novos usuários = cadastros de pessoas.',
                      'Consumo inclui respostas de IA e imagens registradas, inclusive assistências e execuções com falha.',
                      'Custos são estimativas registradas, não a fatura do provedor. Valores sem preço ficam sinalizados.',
                      'Registros antigos usam a data inicial da execução; registros sem data entram apenas no total geral.',
                      'Histórico disponível nos journals; exclusões antigas não podem ser reconstruídas.']}
