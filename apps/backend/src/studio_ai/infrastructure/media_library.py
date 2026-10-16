"""Remove a catalog image into its own store's recoverable trash."""
import json
import threading
from datetime import datetime, timezone
from uuid import uuid4

from . import references
from .persistence.filesystem import media_catalog

_locks = [threading.Lock() for _ in range(64)]


def _contained(root, path):
    if not path.resolve().is_relative_to(root):
        raise ValueError('Arquivo fora da biblioteca da loja')
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('Atalhos não podem ser apagados pela biblioteca')
    return path


def delete_image(root, key, source):
    root = root.resolve()
    with _locks[hash(str(root)) % len(_locks)]:
        reference = None
        if source == 'references':
            reference = next((item for item in references.catalog(root) if item['id'] == key), None)
            if reference is None:
                raise ValueError('Imagem não encontrada')
            image = references.reference_file(root, key)
        elif source == 'media':
            item = media_catalog(root).get(key)
            if item is None:
                raise ValueError('Imagem não encontrada')
            if not item['product'] and item['name'].startswith(('product.', 'reference.', 'brand-reference')):
                raise ValueError('Esta imagem é uma cópia de entrada da campanha')
            image = item['path']
            if item['product']:
                reference = next((ref for ref in references.catalog(root)
                                  if ref['kind'] == 'product' and ref['id'] == image.stem
                                  and references.reference_file(root, ref['id']) == image), None)
        else:
            raise ValueError('Biblioteca inválida')
        files = [image]
        if reference:
            files.append(root / 'campaigns/references' / (reference['id'] + '.json'))
        for path in files:
            _contained(root, path)
        destination = _contained(root, root / '.trash/library' / uuid4().hex)
        moved = []
        try:
            destination.mkdir(parents=True)
            (destination / 'deletion.json').write_text(json.dumps({
                'deleted_at': datetime.now(timezone.utc).isoformat(),
                'files': [path.relative_to(root).as_posix() for path in files],
            }), encoding='utf-8')
            for path in files:
                target = _contained(root, destination / path.relative_to(root))
                target.parent.mkdir(parents=True, exist_ok=True)
                path.rename(target)
                moved.append((path, target))
        except OSError:
            # A metadata failure must not leave a disappearing, half-deleted image.
            for original, target in reversed(moved):
                target.rename(original)
            raise ValueError('Não foi possível apagar a imagem. Tente novamente.') from None
        return {'deleted': key}
