"""Plan or copy legacy store data into data/tenants, retaining every source file.

Stop studio and worker and take a database backup before --apply. This command never
updates PostgreSQL, starts services, deletes sources, or prints file contents.
"""
import argparse
import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
STORE_FOLDERS = ('brand', 'campaigns', 'consultations')
STORE_FILES = ('tenant.json', 'integrations.json')
IGNORED = {'.env', '.env.example', '.model-keys', '.venv', '.pytest_cache', 'README.md', 'tenants'}


def _slug(value):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', value):
        raise ValueError('slug inválido; use letras minúsculas, números e hífens.')
    return value


def _checked_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 1024):
            raise ValueError('Links e junctions não são aceitos na migração.')
    return path.resolve()


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _identity(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _check_entries(entries):
    for item in entries:
        source, target = _checked_path(item['source']), _checked_path(item['target'])
        if not source.is_file() or _digest(source) != item['sha256']:
            raise ValueError('Arquivo de origem mudou; pare os serviços e gere outro plano.')
        if target.exists() and (not target.is_file() or _digest(target) != item['sha256']):
            raise ValueError('Destino contém arquivo diferente; nenhuma origem foi alterada.')
        if any(parent.exists() and not parent.is_dir() for parent in target.parents):
            raise ValueError('Destino contém arquivo diferente no lugar de um diretório.')


def plan_migration(legacy_root, data_root, legacy_tenant,
                   old_runtime_root='/app/realcenter-marketing-ai', runtime_data_root='/app/data'):
    legacy, destination = _checked_path(legacy_root), _checked_path(data_root)
    _slug(legacy_tenant)
    if legacy.is_relative_to(destination) or destination.is_relative_to(legacy):
        raise ValueError('Origem e destino não podem se sobrepor.')
    if not legacy.is_dir():
        raise ValueError('Diretório de origem não encontrado.')
    old_runtime, new_runtime = PurePosixPath(old_runtime_root), PurePosixPath(runtime_data_root)
    if not old_runtime.is_absolute() or not new_runtime.is_absolute() or '..' in (*old_runtime.parts, *new_runtime.parts):
        raise ValueError('Raízes do runtime devem ser caminhos Linux absolutos.')
    stores = [(legacy_tenant, legacy, old_runtime)]
    tenants = legacy / 'tenants'
    if tenants.exists():
        _checked_path(tenants)
        for child in sorted(tenants.iterdir()):
            if not child.is_dir():
                raise ValueError('A pasta tenants contém uma entrada não classificada.')
            _checked_path(child)
            stores.append((_slug(child.name), child, old_runtime / 'tenants' / child.name))
    if len({slug for slug, _, _ in stores}) != len(stores):
        raise ValueError('slug legado já existe em tenants; escolha o proprietário correto.')

    entries, targets, key_names = [], set(), {}

    def add(source, target):
        source, target = _checked_path(source), _checked_path(target)
        if not source.is_relative_to(legacy) or not target.is_relative_to(destination):
            raise ValueError('Arquivo fora das raízes da migração.')
        if target in targets:
            raise ValueError('Dois arquivos apontam para o mesmo destino.')
        targets.add(target)
        entries.append({'source': source, 'target': target, 'sha256': _digest(source),
                        'bytes': source.stat().st_size})

    for slug, source, runtime_source in stores:
        target = destination / 'tenants' / slug
        allowed = set(STORE_FOLDERS + STORE_FILES) | (IGNORED if source == legacy else {'.pytest_cache'})
        if any(child.name not in allowed for child in source.iterdir()):
            raise ValueError('Origem contém entradas não classificadas; revise o layout antes de copiar.')
        for folder in STORE_FOLDERS:
            base = source / folder
            if not base.exists():
                continue
            _checked_path(base)
            if not base.is_dir():
                raise ValueError('Pasta de dados inválida na origem.')
            for file in sorted(base.rglob('*')):
                _checked_path(file)
                if file.is_file() and not file.name.endswith(('.lock', '.tmp')):
                    add(file, target / file.relative_to(source))
        for name in STORE_FILES:
            if (source / name).exists():
                add(source / name, target / name)
        for old_name, new_name in (
            (str(runtime_source), str(new_runtime / 'tenants' / slug)),
            (os.path.normcase(str(source)), os.path.normcase(str(target))),
        ):
            key_names[_identity(old_name)] = _identity(new_name)

    if (legacy / '.env').exists():
        add(legacy / '.env', destination / 'platform/.env')
    keys = legacy / '.model-keys'
    if keys.exists():
        _checked_path(keys)
        for file in sorted(keys.iterdir()):
            if file.name.endswith('.tmp'):
                continue
            if not file.is_file() or file.suffix != '.json' or file.stem not in key_names:
                raise ValueError('Chave privada sem tenant conhecido; revise o mapeamento antes de copiar.')
            add(file, destination / 'platform/.model-keys' / f'{key_names[file.stem]}.json')
    _check_entries(entries)
    return {'entries': entries, 'tenants': len(stores), 'bytes': sum(item['bytes'] for item in entries)}


def apply_migration(plan):
    entries = plan['entries']
    _check_entries(entries)
    copied = 0
    for item in entries:
        source, target = item['source'], item['target']
        _check_entries([item])
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary_name = tempfile.mkstemp(prefix='.migration-', suffix='.tmp', dir=target.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            shutil.copy2(source, temporary)
            if _digest(temporary) != item['sha256']:
                raise ValueError('Arquivo de origem mudou durante a cópia; execute novamente após parar os serviços.')
            # A hard link publishes the complete file without overwriting a concurrent
            # destination. Both names are in the same filesystem; cleanup drops the temp.
            try:
                os.link(temporary, target)
            except FileExistsError:
                _check_entries([item])
            else:
                copied += 1
        finally:
            temporary.unlink(missing_ok=True)
    _check_entries(entries)
    return {'copied': copied, 'existing': len(entries) - copied, 'bytes': plan['bytes']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-root', type=Path, default=ROOT / 'realcenter-marketing-ai')
    parser.add_argument('--data-root', type=Path, default=ROOT / 'data')
    parser.add_argument('--legacy-tenant', required=True, help='Slug da loja proprietária dos dados da raiz antiga')
    parser.add_argument('--old-runtime-root', default='/app/realcenter-marketing-ai')
    parser.add_argument('--runtime-data-root', default='/app/data')
    parser.add_argument('--apply', action='store_true', help='Copiar e verificar; serviços devem estar parados')
    args = parser.parse_args(argv)
    try:
        plan = plan_migration(args.legacy_root, args.data_root, args.legacy_tenant,
                              args.old_runtime_root, args.runtime_data_root)
        print(f"Plano: {plan['tenants']} lojas, {len(plan['entries'])} arquivos, {plan['bytes']} bytes.")
        if args.apply:
            result = apply_migration(plan)
            print(f"Verificados: {result['copied']} copiados, {result['existing']} já existentes. Origens preservadas.")
        else:
            print('Simulação concluída. Nenhum arquivo alterado.')
        return 0
    except ValueError as exc:
        print(f'Migração recusada: {exc}')
        return 1
    except OSError as exc:
        print(f'Migração interrompida: {type(exc).__name__}. Origens preservadas; confira permissões e espaço.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
