"""Backup of the database and of each store's files.

Order matters: the database first, then the directories. A run present on disk but absent
from the database is harmless; the reverse is not, because the row would point at media
that was never captured.

    DATABASE_URL=... python scripts/backup.py --destino /var/backups/studio
"""
import argparse
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/backend/src'))

from realcenter_marketing.bootstrap.paths import AppPaths  # noqa: E402
from realcenter_marketing.infrastructure.identity.database import database_url  # noqa: E402

KEEP_DAILY = 14


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def dump_database(destination, url):
    """pg_dump, never a file copy: copying a live database yields a torn snapshot."""
    if not url:
        print('DATABASE_URL ausente; pulando o banco (instalação standalone).')
        return None
    target = destination / f'studio-{stamp()}.sql'
    if shutil.which('pg_dump') is None:
        raise SystemExit('pg_dump não encontrado. Instale o cliente do PostgreSQL.')
    with target.open('wb') as handle:
        subprocess.run(['pg_dump', '--no-owner', '--no-acl', url], stdout=handle, check=True)
    print(f'Banco: {target.name}')
    return target


def archive_stores(destination, tenants_root, data_root, platform_root=None):
    """One archive per store, so a single store can be restored on its own."""
    roots = []
    if tenants_root.is_dir():
        roots += [path for path in tenants_root.iterdir() if path.is_dir()]
    if data_root not in roots and any((data_root / folder).is_dir() for folder in ('brand', 'campaigns', 'consultations', '.model-keys')):
        roots.append(data_root)
    if platform_root is not None and platform_root not in roots and any(
        (platform_root / name).exists() for name in ('.env', '.model-keys')
    ):
        roots.append(platform_root)
    made = []
    for root in roots:
        prefix = 'platform' if root == platform_root else f'tenant-{root.name}'
        target = destination / f'{prefix}-{stamp()}.tgz'
        skipped = []
        with tarfile.open(target, 'w:gz') as archive:
            for folder in ('brand', 'campaigns', 'consultations', '.model-keys'):
                base = root / folder
                if not base.is_dir():
                    continue
                for path in sorted(base.rglob('*')):
                    if path.is_dir():
                        continue
                    # The lock file is held open by a running server, and a temp file may
                    # vanish mid-walk. Neither is worth failing a backup over.
                    if path.name.endswith(('.lock', '.tmp')):
                        continue
                    try:
                        archive.add(path, arcname=f'{root.name}/{path.relative_to(root).as_posix()}')
                    except (PermissionError, OSError) as exc:
                        skipped.append(f'{path.name} ({type(exc).__name__})')
            extras = ('tenant.json', 'integrations.json') + (('.env',) if root == platform_root else ())
            for extra in extras:
                if (root / extra).is_file():
                    archive.add(root / extra, arcname=f'{root.name}/{extra}')
        made.append(target)
        print(f'Loja: {target.name}' + (f' · {len(skipped)} arquivo(s) em uso ignorado(s)' if skipped else ''))
    return made


def prune(destination, keep=KEEP_DAILY):
    """An unbounded backup directory eventually fills the disk it protects."""
    for prefix in {path.name.rsplit('-', 1)[0] for path in destination.iterdir() if path.is_file()}:
        files = sorted((p for p in destination.iterdir() if p.name.startswith(prefix + '-')),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in files[keep:]:
            stale.unlink()
            print(f'Removido: {stale.name}')


def main():
    parser = argparse.ArgumentParser(description='Backup do Studio')
    parser.add_argument('--destino', type=Path, required=True)
    parser.add_argument('--manter', type=int, default=KEEP_DAILY)
    args = parser.parse_args()
    args.destino.mkdir(parents=True, exist_ok=True)

    paths = AppPaths.discover(None)
    dump_database(args.destino, database_url())
    archive_stores(args.destino, paths.tenants_root, paths.data_root, paths.env_root)
    prune(args.destino, args.manter)
    print('Backup concluído. Teste a restauração periodicamente: um backup nunca restaurado não é backup.')


if __name__ == '__main__':
    main()
