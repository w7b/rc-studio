import hashlib
import json
import re
from pathlib import Path
from realcenter_marketing.application.diagnostics import report

RUN_ID = re.compile(r"run-[a-f0-9]{32}\Z")
OUTPUTS = ('social_media', 'copywriter', 'creative', 'marketing_director', 'campaign', 'brief')


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return default


def run_directory(root, run_id):
    if not RUN_ID.fullmatch(run_id):
        raise ValueError('Execução inválida')
    target = (root / 'campaigns' / 'runs' / run_id).resolve()
    if not target.is_relative_to((root / 'campaigns' / 'runs').resolve()):
        raise ValueError('Execução inválida')
    return target


def media_catalog(root):
    candidates = list((root / 'brand' / 'products' / 'reference-only').rglob('*'))
    candidates += list((root / 'campaigns').glob('*/assets/*'))
    candidates += list((root / 'campaigns' / 'runs').glob('run-*/*.png'))
    candidates += list((root / 'campaigns' / 'runs').glob('run-*/product.jpg'))
    candidates += list((root / 'campaigns' / 'runs').glob('run-*/reference.jpg'))
    candidates += list((root / 'campaigns' / 'runs').glob('run-*/brand-reference.jpg'))
    candidates += list((root / 'campaigns' / 'runs').glob('run-*/brand-reference-*.jpg'))
    candidates += list((root / 'campaigns' / 'runs').glob('run-*/brand-reference-*.webp'))
    result = {}
    for path in candidates:
        if not path.is_file() or path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
            continue
        if not path.resolve().is_relative_to(root.resolve()):
            continue
        relative = path.relative_to(root).as_posix()
        key = hashlib.sha256(relative.encode()).hexdigest()[:24]
        result[key] = {'path': path, 'id': key, 'name': path.name, 'url': '/media/' + key,
                       'product': relative.startswith('brand/products/'), 'run_id': path.parent.name,
                       'created_at': path.stat().st_mtime}
    return result


def snapshot(root, active_id=None):
    result = []
    media = list(media_catalog(root).values())
    directories = sorted((root / 'campaigns' / 'runs').glob('run-*'), key=lambda p: p.name)
    directories.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for directory in directories[:50]:
        if not directory.is_dir() or not RUN_ID.fullmatch(directory.name):
            continue
        events = []
        path = directory / 'events.jsonl'
        if path.exists():
            for line in path.read_text(encoding='utf-8').splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        outputs = {role: value for role in OUTPUTS if (value := read_json(directory / f'{role}.json')) is not None}
        usage = read_json(directory / 'usage.json')
        last = events[-1] if events else {}
        status = 'running' if directory.name == active_id else 'completed' if last.get('event') == 'run_completed' else 'failed' if last.get('event') in ('failed', 'run_failed', 'image_failed') else 'interrupted'
        result.append({'id': directory.name, 'events': events, 'outputs': outputs, 'usage': usage, 'status': status,
                       'diagnostics': report(directory.name, events, usage, outputs),
                       'inputs': [{k: m[k] for k in ('id', 'name', 'url')} for m in media if m['run_id'] == directory.name and m['name'].startswith(('product.', 'reference.', 'brand-reference.', 'brand-reference-'))],
                       'images': [{k: m[k] for k in ('id', 'name', 'url', 'created_at')} for m in sorted(media, key=lambda x: (x['created_at'], x['id'])) if m['run_id'] == directory.name and m['name'].startswith(('feed-', 'story-', 'carousel-', 'reel_cover-'))]})
    return result

from uuid import uuid4
from realcenter_marketing.domain.campaigns import Campaign

def save_campaign(campaign: Campaign, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"campaign-{uuid4().hex}.json"
    with target.open("x", encoding="utf-8") as stream:
        stream.write(campaign.model_dump_json(indent=2))
    return target
