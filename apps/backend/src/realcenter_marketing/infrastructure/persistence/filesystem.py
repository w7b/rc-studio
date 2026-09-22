import hashlib
import json
import threading
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
    candidates = list((root / 'brand' / 'products').rglob('*'))
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
        metadata = read_json(root / 'campaigns/references' / f'{path.stem}.json', {}) if relative.startswith('brand/products/') else {}
        title = metadata.get('title', path.name) if isinstance(metadata, dict) else path.name
        result[key] = {'path': path, 'id': key, 'name': path.name, 'url': '/media/' + key,
                       'title': title,
                       'product': relative.startswith('brand/products/'), 'run_id': path.parent.name,
                       'created_at': path.stat().st_mtime}
    return result


_SNAPSHOT_CACHE = {}
_SNAPSHOT_GUARD = threading.Lock()


def _runs_fingerprint(root):
    """Cheap stand-in for 'has anything changed': the run directory's own mtime plus the
    mtime of each run folder. Directory stats are one syscall each; reading every
    events.jsonl is hundreds."""
    runs = root / 'campaigns' / 'runs'
    try:
        entries = sorted(runs.iterdir())
    except OSError:
        return None
    stamps = [runs.stat().st_mtime]
    for entry in entries[-60:]:
        try:
            stamps.append(entry.stat().st_mtime)
            # The journal is appended to, and appending to an existing file does not
            # touch the parent directory mtime on every platform. Without its size and
            # mtime the cache would keep serving a finished run as still running.
            journal = entry / 'events.jsonl'
            status = journal.stat()
            stamps.append(status.st_mtime)
            stamps.append(status.st_size)
        except OSError:
            continue
        try:
            # Same reasoning as the journal: a rename replaces an existing file, which
            # need not touch the parent directory's mtime, and the cache would keep
            # serving the previous name.
            renamed = (entry / 'title.json').stat()
            stamps.append(renamed.st_mtime)
            stamps.append(renamed.st_size)
        except OSError:
            pass
    return (len(entries), tuple(stamps))


def snapshot(root, active_id=None):
    """Memoised by directory mtime.

    The frontend polls this every two seconds per open tab, and each call used to read
    every events.jsonl of up to fifty runs plus seven globs. With a handful of stores that
    is continuous disk traversal and JSON parsing holding the GIL — it is the first thing
    that gives way under load, well before campaign execution does.
    """
    fingerprint = _runs_fingerprint(root)
    key = str(root)
    if fingerprint is not None:
        with _SNAPSHOT_GUARD:
            cached = _SNAPSHOT_CACHE.get(key)
        if cached and cached[0] == fingerprint:
            # active_id only decides a status label, so it is applied to the cached rows
            # instead of rebuilding everything.
            return [{**run, 'status': 'running' if run['id'] == active_id
                     else ('interrupted' if run['status'] == 'running' else run['status'])}
                    for run in cached[1]]
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
        titled = read_json(directory / 'title.json') or {}
        result.append({'id': directory.name, 'title': titled.get('title'),
                       'events': events, 'outputs': outputs, 'usage': usage, 'status': status,
                       'diagnostics': report(directory.name, events, usage, outputs),
                       'inputs': [{k: m[k] for k in ('id', 'name', 'url')} for m in media if m['run_id'] == directory.name and m['name'].startswith(('product.', 'reference.', 'brand-reference.', 'brand-reference-'))],
                       'images': [{k: m[k] for k in ('id', 'name', 'url', 'created_at')} for m in sorted(media, key=lambda x: (x['created_at'], x['id'])) if m['run_id'] == directory.name and m['name'].startswith(('feed-', 'story-', 'carousel-', 'reel_cover-'))]})
    if fingerprint is not None:
        with _SNAPSHOT_GUARD:
            _SNAPSHOT_CACHE[key] = (fingerprint, result)
    return result

from uuid import uuid4
from realcenter_marketing.domain.campaigns import Campaign

def save_campaign(campaign: Campaign, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"campaign-{uuid4().hex}.json"
    with target.open("x", encoding="utf-8") as stream:
        stream.write(campaign.model_dump_json(indent=2))
    return target
