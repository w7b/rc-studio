"""Login, session and invite rules. Every side effect arrives through a port."""
import hashlib
import hmac
import re
import secrets

from .errors import AccountError, AdminError, AuthError, InviteError, NoAccess, RateLimited
from .model import INVITE_LIFETIME, ROLES, Invite, Principal, now

# Attempts allowed inside a 15 minute window. The per-email budget stops the guessing of
# one account; the per-address budget stops a sweep across many. Both matter because the
# password hash is memory-hard: unbounded logins are a memory exhaustion lever.
EMAIL_ATTEMPTS, ADDRESS_ATTEMPTS, WINDOW_SECONDS = 5, 20, 900

SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{1,39}$')
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MIN_PASSWORD = 8


def token():
    return secrets.token_urlsafe(32)


def token_hash(raw):
    """Sessions and invites are stored hashed, so a database dump cannot be replayed."""
    return hashlib.sha256(raw.encode()).hexdigest()


class IdentityService:
    def __init__(self, store, hasher, limiter, providers=None):
        self.store, self.hasher, self.limiter = store, hasher, limiter
        self.providers = providers or {}

    # -- sign in ---------------------------------------------------------------

    def _guard(self, email, address):
        allowed = self.limiter.hit(f'email:{email.lower()}', EMAIL_ATTEMPTS, WINDOW_SECONDS)
        allowed &= self.limiter.hit(f'addr:{address}', ADDRESS_ATTEMPTS, WINDOW_SECONDS)
        if not allowed:
            raise RateLimited()

    def _first_membership(self, user):
        memberships = self.store.memberships(user.id)
        live = [(tenant, role) for tenant, role in memberships if tenant.active]
        if not live:
            raise NoAccess()
        return live[0]

    def sign_in(self, email, password, address='unknown'):
        self._guard(email, address)
        user = self.store.user_by_email(email)
        encoded = self.store.password_hash(user.id) if user else None
        if user is None or encoded is None or not self.hasher.verify(password, encoded):
            # Spend the same work either way; otherwise the response time answers
            # "does this address have an account here?".
            if user is None or encoded is None:
                self.hasher.dummy_verify()
            raise AuthError('E-mail ou senha inválidos')
        if user.status != 'active':
            raise AuthError('E-mail ou senha inválidos')
        tenant, role = self._first_membership(user)
        self.limiter.reset(f'email:{email.lower()}')
        self.store.touch_login(user.id)
        return self.open_session(user, tenant, role)

    def sign_in_with_profile(self, profile):
        """An OpenID profile authenticates; it never authorizes. Membership is the only
        thing that grants access, so an unknown account is refused rather than onboarded."""
        if not profile.email_verified:
            # Without this, anyone could register the victim's address at the provider
            # and be handed the victim's account.
            raise AuthError('O provedor não confirmou este e-mail')
        user = self.store.user_by_identity(profile.provider, profile.subject)
        if user is None:
            user = self.store.user_by_email(profile.email)
            if user is None:
                raise NoAccess()
            self.store.link_identity(user.id, profile.provider, profile.subject)
        if user.status != 'active':
            raise NoAccess()
        tenant, role = self._first_membership(user)
        self.store.touch_login(user.id)
        return self.open_session(user, tenant, role)

    def open_session(self, user, tenant, role):
        raw, csrf = token(), token()
        session = self.store.create_session(token_hash(raw), user.id, tenant.id, role, csrf)
        return raw, Principal(user=user, tenant=tenant, role=role, session_id=session.id, csrf=csrf)

    # -- session lifecycle -----------------------------------------------------

    def resolve(self, raw):
        """Return the principal for a cookie, or None. Expired sessions are dropped on
        sight so a stale cookie cannot be reused later."""
        if not raw:
            return None
        hashed = token_hash(raw)
        session = self.store.session(hashed)
        if session is None:
            return None
        if session.expired():
            self.store.drop_session(hashed)
            return None
        user, tenant = self.store.user_by_id(session.user_id), self.store.tenant(session.tenant_id)
        if user is None or tenant is None or not tenant.active or user.status != 'active':
            self.store.drop_session(hashed)
            return None
        # Membership can be revoked while a session is open; the cookie must not outlive it.
        role = self.store.membership(user.id, tenant.id)
        if role is None:
            self.store.drop_session(hashed)
            return None
        self.store.touch_session(hashed)
        return Principal(user=user, tenant=tenant, role=role,
                         session_id=session.id, csrf=session.csrf)

    def sign_out(self, raw):
        if raw:
            self.store.drop_session(token_hash(raw))

    def check_csrf(self, principal, presented):
        return bool(principal) and hmac.compare_digest(principal.csrf, presented or '')

    # -- account -----------------------------------------------------------------

    def update_account(self, principal, email=None, name=None, phone=None):
        """Change the signed-in person's own details.

        Changing the address is an identity change, so it has to stay unique and must not
        collide with somebody else's account."""
        user = self.store.user_by_id(principal.user.id)
        if user is None:
            raise AuthError('Conta não encontrada')
        address = (email or user.email).strip()
        if not EMAIL.match(address):
            raise AccountError('Informe um e-mail válido')
        taken = self.store.user_by_email(address)
        if taken is not None and taken.id != user.id:
            raise AccountError('Esse e-mail já está em uso')
        return self.store.update_profile(
            user.id, address,
            (user.name if name is None else name).strip(),
            (user.phone if phone is None else phone).strip())

    def change_password(self, principal, current, replacement):
        """The current password is required even with a valid session: a borrowed
        computer must not be enough to take an account over."""
        encoded = self.store.password_hash(principal.user.id)
        if encoded and not self.hasher.verify(current or '', encoded):
            raise AccountError('Senha atual incorreta')
        if len(replacement or '') < MIN_PASSWORD:
            raise AccountError(f'A nova senha precisa de pelo menos {MIN_PASSWORD} caracteres')
        self.store.set_password(principal.user.id, self.hasher.hash(replacement))
        # Every other session of this account dies, which is the point of changing it.
        self.store.drop_user_sessions(principal.user.id)
        return self.open_session(principal.user, principal.tenant, principal.role)

    # -- administration --------------------------------------------------------

    def overview(self):
        """Every store with its members. Only an OWNER ever calls this."""
        report = []
        for tenant in self.store.tenants():
            members = [
                {'id': user.id, 'email': user.email, 'name': user.name, 'role': role}
                for user, role in self.store.members(tenant.id)
            ]
            report.append({'id': tenant.id, 'slug': tenant.slug, 'name': tenant.name,
                           'status': tenant.status, 'root_path': tenant.root_path,
                           'members': members, 'modules': self.store.modules(tenant.id)})
        return report

    def create_tenant(self, slug, name, root_path=None):
        slug = (slug or '').strip().lower()
        if not SLUG.match(slug):
            raise AdminError('O identificador aceita letras minúsculas, números e hífen (2 a 40).')
        if not (name or '').strip():
            raise AdminError('Informe o nome da loja')
        if self.store.tenant_by_slug(slug):
            raise AdminError('Já existe uma loja com esse identificador')
        return self.store.create_tenant(slug, name.strip(), root_path or None)

    def set_status(self, tenant_id, status):
        if status not in ('active', 'suspended'):
            raise AdminError('Situação inválida')
        tenant = self.store.tenant(tenant_id)
        if tenant is None:
            raise AdminError('Loja não encontrada')
        self.store.set_tenant_status(tenant_id, status)
        if status != 'active':
            # Suspending must take effect now, not whenever the cookies happen to expire.
            for user, _ in self.store.members(tenant_id):
                self.store.drop_user_sessions(user.id)
        return self.store.tenant(tenant_id)

    def set_role(self, user_id, tenant_id, role):
        if role not in ROLES:
            raise AdminError(f'Cargo inválido. Use um destes: {", ".join(ROLES)}.')
        if self.store.membership(user_id, tenant_id) is None:
            raise AdminError('Esse usuário não pertence a esta loja')
        self.store.grant(user_id, tenant_id, role)
        # The role rides inside the session, so an open one would keep the old powers.
        self.store.drop_user_sessions(user_id)
        return role

    def revoke_access(self, user_id, tenant_id):
        if self.store.membership(user_id, tenant_id) is None:
            raise AdminError('Esse usuário não pertence a esta loja')
        self.store.revoke(user_id, tenant_id)
        self.store.drop_user_sessions(user_id)

    # -- invites ---------------------------------------------------------------

    def create_invite(self, tenant_id, role, email=''):
        if role not in ROLES:
            raise InviteError('Papel inválido')
        tenant = self.store.tenant(tenant_id)
        if tenant is None or not tenant.active:
            raise InviteError('Loja indisponível')
        email = str(email).strip().lower()
        if email and (len(email) > 254 or not EMAIL.fullmatch(email)):
            raise InviteError('Informe um e-mail válido para o convite')
        raw = token()
        self.store.create_invite(token_hash(raw), tenant_id, role, email, now() + INVITE_LIFETIME)
        return raw

    def accept_invite(self, raw, password=None, profile=None, name='', email='', address='unknown'):
        hashed = token_hash(raw)
        invite = self.store.invite(hashed)
        if invite is None or not invite.usable():
            raise InviteError('Convite inválido ou expirado')
        if profile is not None and not profile.email_verified:
            raise InviteError('O provedor não confirmou este e-mail')
        email = str(profile.email if profile else (email or invite.email)).strip().lower()
        if len(email) > 254 or not EMAIL.fullmatch(email):
            raise InviteError('Informe um e-mail válido para aceitar o convite')
        if invite.email and email != invite.email.strip().lower():
            raise InviteError('Use o e-mail que recebeu este convite')
        self._guard(email, address)
        tenant = self.store.tenant(invite.tenant_id)
        if tenant is None or not tenant.active:
            raise InviteError('Loja indisponível')
        user = self.store.user_by_email(email)
        if user is None:
            if profile is None and (not password or len(password) < MIN_PASSWORD):
                raise InviteError(f'A nova senha precisa de pelo menos {MIN_PASSWORD} caracteres')
            encoded = self.hasher.hash(password) if password else None
            user = self.store.create_user(email, encoded, name or (profile.name if profile else ''))
        else:
            if user.status != 'active':
                raise InviteError('Não foi possível aceitar este convite com esta conta')
            if profile is None:
                encoded = self.store.password_hash(user.id)
                if not encoded or not password or not self.hasher.verify(password, encoded):
                    raise InviteError('Este e-mail já tem conta. Informe sua senha atual para aceitar o convite')
        if profile is not None:
            self.store.link_identity(user.id, profile.provider, profile.subject)
        # Claimed last: if two people open the same link, only one transaction wins.
        if not self.store.consume_invite(hashed):
            raise InviteError('Convite já utilizado')
        self.store.grant(user.id, invite.tenant_id, invite.role)
        self.limiter.reset(f'email:{email}')
        return self.open_session(user, tenant, invite.role)
