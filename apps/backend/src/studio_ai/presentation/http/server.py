import argparse
import signal
import json
import mimetypes
import os
import secrets
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pydantic import ValidationError

from studio_ai.domain.consultations import ConsultationRequest
from studio_ai.application.commands import RenameRequest, AssistRequest, ImageRequest, RunRequest, ReferenceRequest, ReferenceEditRequest
from studio_ai.application.errors import BusyError
from studio_ai.application.identity.errors import (
    AccountError, AdminError, AuthError, InviteError, RateLimited)
from studio_ai.application.identity.model import ABSOLUTE_LIFETIME, ROLES
from studio_ai.application.identity.quota import QuotaError
from studio_ai.application.identity.modules import MODULES, required_modules
from studio_ai.domain.publications import catalog as publication_catalog
from . import cookies, proxy


def spa_route(path):
    """Client-side routes that must serve the app shell instead of 404.

    A dot in the last segment disqualifies the path, which is what keeps /.env and
    /assets/../../.env answering 404 rather than handing back index.html."""
    if path.startswith(('/api/', '/media/', '/assets/')) or not path.startswith('/'):
        return False
    return '.' not in path.rsplit('/', 1)[-1] and '..' not in path


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, token, identity=None, **kwargs):
        self.token, self.identity = token, identity
        self._principal, self._resolved, self._context = None, False, None
        super().__init__(*args, **kwargs)

    def reply(self, status, body, mime='application/json; charset=utf-8', download=None, headers=()):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'")
        if download:
            self.send_header('Content-Disposition', f'attachment; filename="{download}"')
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass
        return True

    def redirect(self, location, headers=()):
        self.send_response(303)
        self.send_header('Location', location)
        self.send_header('Content-Length', '0')
        self.send_header('Cache-Control', 'no-store')
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()

    # -- identity --------------------------------------------------------------

    @property
    def shared(self):
        """A deployment without a database keeps the original single-user behaviour."""
        return self.identity is not None

    def principal(self):
        if not self._resolved:
            self._resolved = True
            if self.shared:
                raw = cookies.read(self.headers.get('Cookie'), cookies.SESSION_COOKIE)
                self._principal = self.identity.service.resolve(raw)
        return self._principal

    def context(self):
        """The store this request answers for.

        The root is derived from the session, never from the path or a query parameter.
        That is the whole isolation guarantee: media and reference ids collide between
        stores by construction, so an id must never be resolved by searching."""
        if self._context is None:
            principal = self.principal()
            if principal is None:
                self._context = self.server.container.standalone
            else:
                self._context = self.server.container.registry.context(
                    principal.tenant.slug, principal.tenant.root_path,
                    tenant_id=principal.tenant.id, role=principal.role)
        return self._context

    def session_cookie(self, raw):
        return [('Set-Cookie', cookies.build(cookies.SESSION_COOKIE, raw,
                                             int(ABSOLUTE_LIFETIME.total_seconds()),
                                             self.server.public_scheme))]

    def public_origin(self):
        return f'{self.server.public_scheme}://{self.headers.get("Host", "")}'

    def auth_get(self, path):
        """Session and OAuth reads. Returns a truthy marker once it has answered."""
        if path == '/api/session':
            principal = self.principal()
            if principal is None:
                return self.reply(200, {'authenticated': False}) or True
            return self.reply(200, {
                'authenticated': True,
                'csrf': principal.csrf,
                'user': {'name': principal.user.name, 'email': principal.user.email,
                         'phone': principal.user.phone},
                'tenant': {'slug': principal.tenant.slug, 'name': principal.tenant.name,
                           'brand_color': self.context().brand_color()},
                'role': principal.role,
                'modules': self.identity.service.store.modules(principal.tenant.id),
                'providers': sorted(self.identity.providers),
                'quota': self.context().quota_summary(),
            }) or True
        if path == '/api/admin/overview':
            if not self.owner():
                return self.reply(403, {'error': 'Área restrita ao administrador'}) or True
            tenants = self.identity.service.overview()
            for tenant in tenants:
                tenant['meta_ads'] = self.server.container.registry.integration_status(tenant['slug'], tenant['root_path'])['meta_ads']
            return self.reply(200, {'tenants': tenants, 'roles': list(ROLES),
                                    'modules': MODULES}) or True
        if path == '/api/admin/metrics':
            if not self.owner():
                return self.reply(403, {'error': 'Área restrita ao administrador'}) or True
            return self.reply(200, self.server.container.admin_metrics(self.identity.service.store)) or True
        if path == '/api/admin/tenants/model-keys':
            if not self.owner():
                return self.reply(403, {'error': 'Área restrita ao administrador'}) or True
            try:
                tenant_id = parse_qs(urlsplit(self.path).query).get('tenant_id', ['0'])[0]
                tenant = self.identity.service.store.tenant(int(tenant_id))
                if tenant is None:
                    raise ValueError('Loja não encontrada')
                return self.reply(200, self.server.container.model_keys(tenant)) or True
            except ValueError:
                return self.reply(400, {'error': 'Não foi possível consultar as chaves desta loja'}) or True
        parts = path.strip('/').split('/')
        if len(parts) == 3 and parts[:2] == ['api', 'auth']:
            return self.start_oauth(parts[2]) or True
        if len(parts) == 4 and parts[:2] == ['api', 'auth'] and parts[3] == 'callback':
            return self.finish_oauth(parts[2]) or True
        return None

    def start_oauth(self, name):
        provider = self.identity.providers.get(name)
        if provider is None:
            return self.reply(404, {'error': 'Login com o Google não está configurado'})
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        redirect = f'{self.public_origin()}/api/auth/{name}/callback'
        # state and verifier ride in a short-lived cookie: state proves the callback
        # belongs to a flow this browser started, PKCE proves the code was not lifted.
        jar = cookies.build(cookies.OAUTH_COOKIE, f'{state}.{verifier}', 600, self.server.public_scheme)
        return self.redirect(provider.authorization_url(state, verifier, redirect),
                             [('Set-Cookie', jar)])

    def finish_oauth(self, name):
        provider = self.identity.providers.get(name)
        query = parse_qs(urlsplit(self.path).query)
        stored = cookies.read(self.headers.get('Cookie'), cookies.OAUTH_COOKIE) or ''
        drop = ('Set-Cookie', cookies.expire(cookies.OAUTH_COOKIE, self.server.public_scheme))
        state, _, verifier = stored.partition('.')
        code = (query.get('code') or [''])[0]
        if provider is None or not verifier or not code or not state or not secrets.compare_digest((query.get('state') or [''])[0], state):
            return self.redirect('/login?erro=oauth', [drop])
        try:
            profile = provider.exchange(code, verifier, f'{self.public_origin()}/api/auth/{name}/callback')
        except AuthError:
            return self.redirect('/login?erro=oauth', [drop])
        try:
            raw, _ = self.identity.service.sign_in_with_profile(profile)
        except AuthError:
            return self.redirect('/login?erro=sem-acesso', [drop])
        return self.redirect('/studio', [drop, *self.session_cookie(raw)])

    def modules(self):
        if not self.shared:
            return dict.fromkeys(MODULES, True)
        principal = self.principal()
        return self.identity.service.store.modules(principal.tenant.id) if principal else {}

    def module_allowed(self, path, payload=None):
        required = required_modules(path, payload)
        enabled = self.modules() if required else {}
        return not required or any(enabled.get(key, False) for key in required)

    def local_host(self):
        return self.headers.get('Host') in self.server.allowed_hosts

    def origin_ok(self):
        """The Origin must match the public origin. A missing Origin is tolerated only
        for requests that carry no cookie: browsers always send Origin on cross-site
        POST, so the gap is reachable only by non-browser clients (CLI, smoke tests),
        which never hold someone else's session. Once auth moves to cookies, those
        requests become strict automatically."""
        origin = self.headers.get('Origin')
        if origin is None:
            return 'Cookie' not in self.headers
        return origin == f'{self.server.public_scheme}://{self.headers.get("Host", "")}'

    def do_GET(self):
        if not self.local_host():
            return self.reply(403, {'error': 'Host inválido'})
        path = urlsplit(self.path).path
        if self.shared:
            answered = self.auth_get(path)
            if answered:
                return answered
            # Everything past this point reads campaign data, so it needs a session.
            # /api/config and the static shell stay public: the login page is served
            # from them, and neither carries anything belonging to a store.
            if path.startswith(('/api/', '/media/')) and path != '/api/config':
                if self.principal() is None:
                    return self.reply(401, {'error': 'Sessão expirada'})
                if path.startswith(('/api/logs', '/api/usage')) and not self.principal().is_owner:
                    return self.reply(403, {'error': 'Área restrita ao administrador'})
                if not self.module_allowed(path):
                    return self.reply(403, {'error': 'Módulo desativado para esta loja'})
        context = self.context()
        queries = context.queries
        if path == '/api/logs':
            if self.shared and not self.owner():
                return self.reply(403, {'error': 'Área restrita ao administrador'})
            return self.reply(200, self.platform_logs())
        if path == '/api/system/activity':
            return self.reply(200, queries.activity())
        if path == '/api/usage':
            return self.reply(200, queries.usage())
        if path == '/api/integrations':
            enabled = self.modules()
            return self.reply(200, {key: value for key, value in self.context().integrations().items() if enabled.get(key)})
        if path == '/api/store':
            return self.reply(200, self.context().store_profile())
        if path == '/api/brandkit':
            return self.reply(200, self.context().brand_kit())
        if path == '/api/formats':
            formats = self.server.container.cache.get_or_set(
                'formats', 3600, publication_catalog)
            return self.reply(200, formats)
        if path == '/api/references':
            return self.reply(200, queries.references())
        if path == '/api/references/editor-options':
            return self.reply(200, queries.reference_editor_options())
        reference_parts = path.strip('/').split('/')
        if len(reference_parts) == 4 and reference_parts[:2] == ['api', 'references'] and reference_parts[3] in ('image', 'download'):
            try:
                content, name = queries.reference_file(reference_parts[2])
                return self.reply(200, content, mimetypes.guess_type(name)[0], name if reference_parts[3] == 'download' else None)
            except (ValueError, OSError):
                return self.reply(404, {'error': 'Referência não encontrada'})
        if path == '/api/config':
            # In a shared deployment the CSRF token belongs to a session and is handed
            # out by /api/session. Serving it here would mean serving it before login.
            context = self.context()
            public = self.server.container.cache.get_or_set(
                f'config:{context.slug}', 60, context.public_config)
            if self.shared:
                return self.reply(200, {**public, 'shared': True,
                                        'providers': sorted(self.identity.providers)})
            return self.reply(200, {'token': self.token, **public})
        if path == '/api/runs':
            return self.reply(200, context.run_state())
        if path == '/api/media':
            return self.reply(200, queries.media())
        if path.startswith('/media/'):
            try:
                content, name = queries.media_file(path[7:])
                return self.reply(200, content, mimetypes.guess_type(name)[0] or 'application/octet-stream')
            except (ValueError, OSError):
                return self.reply(404, {'error': 'Não encontrado'})
        parts = path.strip('/').split('/')
        if len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'draft':
            try:
                return self.reply(200, context.service.saved_request(parts[2]).model_dump())
            except (ValueError, OSError):
                return self.reply(404, {'error': 'Briefing não encontrado'})
        if len(parts) == 5 and parts[:2] == ['api', 'runs'] and parts[3] == 'files':
            try:
                content, mime = queries.artifact(parts[2], parts[4])
                return self.reply(200, content, mime, download=parts[4])
            except (ValueError, OSError):
                pass
        static = self.server.paths.static_root
        file = static / 'index.html' if path == '/' else (static / path.lstrip('/')).resolve() if path.startswith('/assets/') else None
        if file and file.resolve().is_relative_to(static.resolve()) and file.is_file():
            return self.reply(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
        if spa_route(path):
            shell = static / 'index.html'
            if shell.is_file():
                return self.reply(200, shell.read_bytes(), 'text/html; charset=utf-8')
        return self.reply(404, {'error': 'Não encontrado'})

    def body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 23 * 1024 * 1024:
            raise ValueError('Upload excedeu o limite')
        return json.loads(self.rfile.read(length))

    def auth_post(self, path):
        """Sign-in routes. They run before the CSRF gate because they are what mints the
        token, so Origin plus the rate limiter carry the defence here."""
        if path not in ('/api/login', '/api/logout', '/api/invites/accept'):
            return None
        if path == '/api/logout':
            self.identity.service.sign_out(cookies.read(self.headers.get('Cookie'), cookies.SESSION_COOKIE))
            return self.reply(200, {'ok': True}, headers=[
                ('Set-Cookie', cookies.expire(cookies.SESSION_COOKIE, self.server.public_scheme))]) or True
        try:
            payload = self.body()
            address = proxy.client_address(self.client_address[0], self.headers.get('X-Real-IP'),
                                           self.server.trusted_proxies)
            if path == '/api/login':
                raw, principal = self.identity.service.sign_in(
                    str(payload.get('email', '')).strip(), str(payload.get('password', '')),
                    address=address)
            else:
                raw, principal = self.identity.service.accept_invite(
                    str(payload.get('token', '')), password=str(payload.get('password', '')) or None,
                    name=str(payload.get('name', '')).strip(), email=str(payload.get('email', '')).strip(),
                    address=address)
        except RateLimited as exc:
            return self.reply(429, {'error': str(exc)}, headers=[('Retry-After', str(exc.retry_after))]) or True
        except AuthError as exc:
            return self.reply(401, {'error': str(exc)}) or True
        except InviteError as exc:
            return self.reply(400, {'error': str(exc)}) or True
        except (ValueError, json.JSONDecodeError):
            return self.reply(400, {'error': 'Confira os campos enviados'}) or True
        return self.reply(200, {'ok': True, 'csrf': principal.csrf,
                                'tenant': {'slug': principal.tenant.slug, 'name': principal.tenant.name}},
                          headers=self.session_cookie(raw)) or True

    def platform_logs(self):
        """Recent activity. An owner sees every store, because a platform-wide failure is
        exactly what they are looking for; anyone else sees only their own."""
        if not self.shared:
            return {'scope': 'local', 'entries': self.context().queries.activity()}
        entries = []
        for tenant in self.identity.service.store.tenants():
            context = self.server.container.registry.context(tenant.slug, tenant.root_path)
            for event in context.queries.activity():
                entries.append({'tenant': tenant.slug, **event})
        entries.sort(key=lambda item: item.get('time', ''), reverse=True)
        return {'scope': 'platform', 'entries': entries[:400]}

    def owner(self):
        principal = self.principal()
        return principal is not None and principal.is_owner

    def admin_post(self, path, payload):
        """Management actions. Every one of them is refused to anyone but an OWNER."""
        service = self.identity.service
        if path == '/api/admin/tenants/model-keys':
            tenant = service.store.tenant(int(payload.get('tenant_id', 0)))
            if tenant is None:
                raise AdminError('Loja não encontrada')
            container = self.server.container
            try:
                updated = container.save_model_keys(tenant, payload.get('changes'))
            except ValueError as exc:
                raise AdminError(str(exc)) from None
            except OSError:
                raise AdminError('Não foi possível salvar as chaves. Tente novamente.') from None
            return self.reply(200, updated)
        if path in ('/api/admin/tenants/modules', '/api/admin/tenants/meta-ads/validate'):
            tenant = service.store.tenant(int(payload.get('tenant_id', 0)))
            if tenant is None:
                raise AdminError('Loja não encontrada')
            if path.endswith('/modules'):
                module, enabled = payload.get('module'), payload.get('enabled')
                if module not in MODULES or type(enabled) is not bool:
                    raise AdminError('Informe um módulo válido e se deve estar ativo')
                service.store.set_module(tenant.id, module, enabled)
                return self.reply(200, {'modules': service.store.modules(tenant.id)})
            if not service.store.modules(tenant.id)['meta_ads']:
                raise AdminError('Módulo Meta Ads desativado para esta loja')
            return self.reply(200, self.server.container.registry.validate_meta(tenant.slug, tenant.root_path))
        if path == '/api/admin/tenants':
            tenant = service.create_tenant(payload.get('slug'), payload.get('name'),
                                           payload.get('root_path'))
            # Seed the store's own profile so it starts with an identity instead of a
            # blank one that would omit its address from every caption.
            seed = {key: payload.get(key) for key in
                    ('segment', 'city', 'address', 'phone', 'whatsapp', 'instagram',
                     'brand_color', 'claim_pack') if payload.get(key)}
            context = self.server.container.registry.context(tenant.slug, tenant.root_path)
            context.save_store_profile({'brand_name': tenant.name, **seed})
            # Without a Brand Kit the first campaign dies at load_brand with "Brand Kit
            # ausente", after the owner has already filled in the whole form. Seeding it
            # from the neutral base means the store is usable the moment it exists.
            created = context.seed_brand_kit()['created']
            return self.reply(201, {'id': tenant.id, 'slug': tenant.slug, 'name': tenant.name,
                                    'brand_kit': created})
        if path == '/api/admin/tenants/status':
            tenant = service.set_status(int(payload.get('tenant_id', 0)), payload.get('status'))
            return self.reply(200, {'id': tenant.id, 'status': tenant.status})
        if path == '/api/admin/memberships':
            role = service.set_role(int(payload.get('user_id', 0)),
                                    int(payload.get('tenant_id', 0)), payload.get('role'))
            return self.reply(200, {'role': role})
        if path == '/api/admin/memberships/revoke':
            service.revoke_access(int(payload.get('user_id', 0)), int(payload.get('tenant_id', 0)))
            return self.reply(200, {'ok': True})
        if path == '/api/admin/invites':
            token = service.create_invite(int(payload.get('tenant_id', 0)),
                                          payload.get('role', 'DEFAULT'), payload.get('email', ''))
            # Returned once. The token is stored hashed, so it cannot be shown again.
            return self.reply(201, {'link': f'{self.public_origin()}/convite#{token}'})
        return None

    def integrations_post(self, payload):
        module = str(payload.get('module', ''))
        updated = self.context().save_integration(module, payload.get('values') or {})
        return self.reply(200, {key: value for key, value in updated.items() if self.modules().get(key)})

    def account_post(self, path, payload):
        """The signed-in person editing their own details."""
        service, principal = self.identity.service, self.principal()
        if path == '/api/account':
            user = service.update_account(principal, email=payload.get('email'),
                                          name=payload.get('name'), phone=payload.get('phone'))
            return self.reply(200, {'name': user.name, 'email': user.email, 'phone': user.phone})
        if path == '/api/account/password':
            raw, updated = service.change_password(principal, payload.get('current'),
                                                   payload.get('password'))
            # Changing the password invalidates every session, so this one is reissued.
            return self.reply(200, {'ok': True, 'csrf': updated.csrf},
                              headers=self.session_cookie(raw))
        return None

    def do_POST(self):
        if not self.local_host() or not self.origin_ok():
            return self.reply(403, {'error': 'Recarregue o app para iniciar a execução'})
        if self.shared:
            answered = self.auth_post(urlsplit(self.path).path)
            if answered:
                return answered
            principal = self.principal()
            if principal is None:
                return self.reply(401, {'error': 'Sessão expirada'})
            # The CSRF token belongs to this session, so one store's token can never
            # authorize a write for another.
            if not self.identity.service.check_csrf(principal, self.headers.get('X-App-Token', '')):
                return self.reply(403, {'error': 'Recarregue o app para iniciar a execução'})
        elif not secrets.compare_digest(self.headers.get('X-App-Token', ''), self.token):
            return self.reply(403, {'error': 'Recarregue o app para iniciar a execução'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply(415, {'error': 'Envie JSON'})
        if self.shared and urlsplit(self.path).path.startswith('/api/account'):
            try:
                answered = self.account_post(urlsplit(self.path).path, self.body())
            except AccountError as exc:
                return self.reply(400, {'error': str(exc)})
            except AuthError as exc:
                return self.reply(401, {'error': str(exc)})
            except (ValueError, json.JSONDecodeError):
                return self.reply(400, {'error': 'Confira os campos enviados'})
            if answered is not None:
                return answered
            return self.reply(404, {'error': 'Não encontrado'})
        if self.shared and urlsplit(self.path).path.startswith('/api/admin/'):
            try:
                # Read the body before answering, even to refuse. Replying while the
                # client is still sending aborts the connection, and the caller sees a
                # transport error instead of the 403 it needs to act on.
                payload = self.body()
            except (ValueError, json.JSONDecodeError):
                payload = None
            if not self.owner():
                return self.reply(403, {'error': 'Área restrita ao administrador'})
            if payload is None:
                return self.reply(400, {'error': 'Confira os campos enviados'})
            try:
                answered = self.admin_post(urlsplit(self.path).path, payload)
            except AdminError as exc:
                return self.reply(400, {'error': str(exc)})
            except (ValueError, json.JSONDecodeError):
                return self.reply(400, {'error': 'Confira os campos enviados'})
            if answered is not None:
                return answered
            return self.reply(404, {'error': 'Não encontrado'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 23 * 1024 * 1024:
                return self.reply(413, {'error': 'Upload excedeu o limite'})
            payload = json.loads(self.rfile.read(length))
            path = urlsplit(self.path).path
            if not self.module_allowed(path, payload):
                return self.reply(403, {'error': 'Módulo desativado para esta loja'})
            if path == '/api/integrations/meta-ads/validate':
                return self.reply(200, self.context().validate_meta())
            if path == '/api/consultations':
                return self.reply(200, self.context().consult(ConsultationRequest.model_validate(payload)))
            if path == '/api/brief-assist':
                return self.reply(200, self.context().service.assist(AssistRequest.model_validate(payload)))
            if path == '/api/integrations':
                return self.integrations_post(payload)
            if path == '/api/store':
                return self.reply(200, self.context().save_store_profile(payload))
            if path == '/api/brandkit':
                return self.reply(200, self.context().save_brand_kit(
                    str(payload.get('name', '')), payload.get('content')))
            if path == '/api/brandkit/seed':
                return self.reply(200, self.context().seed_brand_kit(
                    overwrite=bool(payload.get('overwrite'))))
            if path == '/api/references':
                return self.reply(201, self.context().queries.save_reference(ReferenceRequest.model_validate(payload)))
            if path == '/api/references/edit':
                return self.reply(201, self.context().queries.edit_reference(ReferenceEditRequest.model_validate(payload)))
            if path == '/api/runs':
                run_id = self.context().service.start(RunRequest.model_validate(payload))
                return self.reply(202, {'id': run_id})
            parts = path.strip('/').split('/')
            if len(parts) == 4 and parts[0] == 'api' and parts[1] in ('media', 'references') and parts[3] == 'delete':
                return self.reply(200, self.context().delete_image(parts[2], parts[1]))
            if len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'retry':
                return self.reply(202, {'id': self.context().service.retry(parts[2])})
            if len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'rename':
                title = self.context().service.set_title(parts[2], RenameRequest.model_validate(payload).title)
                return self.reply(200, {'id': parts[2], 'title': title})
            if len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'delete':
                self.context().service.delete(parts[2])
                return self.reply(200, {'deleted': parts[2]})
            if len(parts) == 4 and parts[:2] == ['api', 'runs'] and parts[3] == 'image':
                self.context().service.image(parts[2], ImageRequest.model_validate(payload))
                return self.reply(202, {'id': parts[2]})
            return self.reply(404, {'error': 'Não encontrado'})
        except BusyError as exc:
            return self.reply(409, {'error': str(exc)})
        except QuotaError as exc:
            return self.reply(402, exc.details())
        except ValidationError:
            return self.reply(400, {'error': 'Confira o briefing e os campos enviados'})
        except (ValueError, json.JSONDecodeError) as exc:
            message = str(exc) if type(exc) is ValueError else 'JSON inválido'
            return self.reply(400, {'error': message[:180]})
        except Exception:
            return self.reply(500, {'error': 'Não foi possível iniciar a execução'})

    def log_message(self, *args):
        pass


class StudioServer(ThreadingHTTPServer):
    def server_close(self):
        super().server_close()
        try:
            if hasattr(self, 'container'):
                self.container.close()
        finally:
            if getattr(self, 'identity', None) is not None:
                self.identity.close()


def public_hosts(port):
    """Hosts this server answers for. Behind a TLS proxy the browser sends the public
    name, not the loopback pair, so it has to be declared."""
    hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
    for entry in os.environ.get('REALCENTER_PUBLIC_HOST', '').split(','):
        if entry.strip():
            hosts.add(entry.strip())
    return hosts


def make_server(root=None, port=8765, host='127.0.0.1', identity=None):
    from studio_ai.bootstrap.container import build_container
    from studio_ai.bootstrap.platform import build_identity
    identity = identity if identity is not None else build_identity()
    container = build_container(root, quota_for=getattr(identity, 'quota_for', None),
                                queue_for=getattr(identity, 'queue_for', None))
    try:
        server = StudioServer((host, port), partial(Handler, token=secrets.token_urlsafe(32),
                                                    identity=identity))
        server.container, server.identity = container, identity
        server.paths, server.service = container.paths, container.service
        # The scheme cannot be derived from the socket: TLS terminates at the proxy, so
        # deriving it would reject every POST from an https browser.
        server.public_scheme = os.environ.get('REALCENTER_PUBLIC_SCHEME', 'http')
        server.allowed_hosts = public_hosts(server.server_port)
        server.trusted_proxies = tuple(value.strip() for value in
                                       os.environ.get('REALCENTER_TRUSTED_PROXIES', '').split(',')
                                       if value.strip())
        return server
    except BaseException:
        try:
            container.close()
        finally:
            if identity is not None:
                identity.close()
        raise


def main():
    parser = argparse.ArgumentParser(description='Studio — app de campanhas')
    parser.add_argument('--project-root', type=Path, default=None)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', choices=['127.0.0.1', '0.0.0.0'], default='127.0.0.1')
    args = parser.parse_args()
    server = make_server(args.project_root, args.port, args.host)
    print(f'Studio: http://127.0.0.1:{args.port}', flush=True)
    def terminate(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, terminate)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous)
        server.server_close()


if __name__ == '__main__':
    main()
