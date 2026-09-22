"""Bootstrap and manage stores and accounts from the command line.

The first store and the first owner have to exist before anyone can sign in, and there
is no mail server, so invites are links the operator sends by hand.

    python scripts/admin.py loja criar mercado-central "Mercado Central"
    python scripts/admin.py usuario criar dono@loja.com.br --loja mercado-central --papel owner
    python scripts/admin.py convite criar --loja mercado-central --papel editor --email novo@loja.com.br
    python scripts/admin.py listar
"""
import argparse
import getpass
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/backend/src'))

from realcenter_marketing.application.identity.model import ROLES  # noqa: E402
from realcenter_marketing.application.identity.service import MIN_PASSWORD  # noqa: E402
from realcenter_marketing.bootstrap.platform import build_identity  # noqa: E402

SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{1,39}$')


def identity_or_exit():
    identity = build_identity()
    if identity is None:
        raise SystemExit('Defina DATABASE_URL para administrar a implantação compartilhada.')
    return identity


def ask_password():
    password = os.environ.get('STUDIO_PASSWORD') or getpass.getpass('Senha: ')
    if len(password) < MIN_PASSWORD:
        raise SystemExit(f'A senha precisa de pelo menos {MIN_PASSWORD} caracteres.')
    return password


def create_tenant(identity, args):
    if not SLUG.match(args.slug):
        raise SystemExit('O identificador aceita apenas letras minúsculas, números e hífen.')
    store = identity.service.store
    if store.tenant_by_slug(args.slug):
        raise SystemExit(f'A loja {args.slug} já existe.')
    tenant = store.create_tenant(args.slug, args.nome, args.raiz)
    print(f'Loja criada: {tenant.slug} (id {tenant.id})')


def create_user(identity, args):
    if args.papel not in ROLES:
        raise SystemExit(f'Papel inválido. Use um destes: {", ".join(ROLES)}.')
    store = identity.service.store
    tenant = store.tenant_by_slug(args.loja)
    if tenant is None:
        raise SystemExit(f'Loja {args.loja} não encontrada.')
    user = store.user_by_email(args.email)
    if user is None:
        user = store.create_user(args.email, identity.service.hasher.hash(ask_password()), args.nome or '')
        print(f'Usuário criado: {user.email} (id {user.id})')
    store.grant(user.id, tenant.id, args.papel)
    print(f'Acesso concedido: {user.email} -> {tenant.slug} como {args.papel}')


def create_invite(identity, args):
    store = identity.service.store
    tenant = store.tenant_by_slug(args.loja)
    if tenant is None:
        raise SystemExit(f'Loja {args.loja} não encontrada.')
    token = identity.service.create_invite(tenant.id, args.papel, args.email or '')
    base = args.url.rstrip('/')
    # The token lives in the fragment: browsers never send it to a server, so it stays
    # out of proxy logs and out of Referer headers.
    print(f'Envie este link (validade de 7 dias, uso único):\n{base}/convite#{token}')


def listing(identity, _args):
    store = identity.service.store
    for tenant in store.tenants():
        print(f'{tenant.slug:24} {tenant.name:30} {tenant.status}')


def main():
    parser = argparse.ArgumentParser(description='Administração do Studio compartilhado')
    commands = parser.add_subparsers(dest='grupo', required=True)

    tenant = commands.add_parser('loja').add_subparsers(dest='acao', required=True)
    new_tenant = tenant.add_parser('criar')
    new_tenant.add_argument('slug')
    new_tenant.add_argument('nome')
    new_tenant.add_argument('--raiz', default=None, help='Raiz de dados existente, se houver')
    new_tenant.set_defaults(run=create_tenant)

    user = commands.add_parser('usuario').add_subparsers(dest='acao', required=True)
    new_user = user.add_parser('criar')
    new_user.add_argument('email')
    new_user.add_argument('--loja', required=True)
    new_user.add_argument('--papel', default='OWNER')
    new_user.add_argument('--nome', default='')
    new_user.set_defaults(run=create_user)

    invite = commands.add_parser('convite').add_subparsers(dest='acao', required=True)
    new_invite = invite.add_parser('criar')
    new_invite.add_argument('--loja', required=True)
    new_invite.add_argument('--papel', default='DEFAULT')
    new_invite.add_argument('--email', default='')
    new_invite.add_argument('--url', default='http://127.0.0.1:8765')
    new_invite.set_defaults(run=create_invite)

    commands.add_parser('listar').set_defaults(run=listing)

    args = parser.parse_args()
    identity = identity_or_exit()
    try:
        args.run(identity, args)
    finally:
        identity.close()


if __name__ == '__main__':
    main()
