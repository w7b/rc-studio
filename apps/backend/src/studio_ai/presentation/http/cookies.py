"""Session cookie encoding. Standard library only, no infrastructure imports."""
import os
from http.cookies import SimpleCookie

SESSION_COOKIE = 'rcs_session'
OAUTH_COOKIE = 'rcs_oauth'


def secure_cookies(scheme='http'):
    """Secure is mandatory in production and impossible in the local suite, which speaks
    plain HTTP to 127.0.0.1. The public scheme decides, and an operator can force it."""
    configured = os.environ.get('REALCENTER_COOKIE_SECURE')
    if configured in ('0', '1'):
        return configured == '1'
    return scheme == 'https'


def read(header, name):
    if not header:
        return None
    jar = SimpleCookie()
    try:
        jar.load(header)
    except Exception:
        return None
    entry = jar.get(name)
    return entry.value if entry else None


def build(name, value, max_age, scheme='http', path='/'):
    # SameSite=Lax still allows the top-level navigation back from an OAuth provider,
    # while keeping the cookie off cross-site POSTs.
    parts = [f'{name}={value}', f'Path={path}', f'Max-Age={max_age}', 'HttpOnly', 'SameSite=Lax']
    if secure_cookies(scheme):
        parts.append('Secure')
    return '; '.join(parts)


def expire(name, scheme='http', path='/'):
    return build(name, '', 0, scheme, path)
