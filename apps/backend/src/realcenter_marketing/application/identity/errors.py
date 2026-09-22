"""Failures the HTTP layer maps to status codes."""


class AuthError(Exception):
    """Credentials were not accepted. The message is deliberately uniform."""


class RateLimited(AuthError):
    def __init__(self, retry_after=900):
        super().__init__('Muitas tentativas. Tente novamente mais tarde.')
        self.retry_after = retry_after


class NoAccess(AuthError):
    """Authenticated, but not a member of any store. Never auto-provision here: a
    provider account proves who someone is, never that they bought anything."""

    def __init__(self, message='Sua conta não tem acesso a nenhuma loja. Peça um convite ao administrador.'):
        super().__init__(message)


class InviteError(Exception):
    pass


class AdminError(Exception):
    """A management action the operator asked for cannot be carried out as stated."""


class AccountError(Exception):
    """The person's own account change cannot be applied as asked."""
