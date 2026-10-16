"""Google sign-in over OpenID Connect, Authorization Code with PKCE.

No JWT library is needed. The code is exchanged server to server, over TLS, against
Google's own token endpoint using the client secret, so the response is trusted because
of where it came from rather than because of a signature this process verified. That
removes an RSA dependency without weakening the flow.
"""
import base64
import hashlib
import json
import os
import secrets
import urllib.parse
import urllib.request

from studio_ai.application.identity.errors import AuthError
from studio_ai.application.identity.model import OAuthProfile

AUTHORIZATION_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
USERINFO_ENDPOINT = 'https://openidconnect.googleapis.com/v1/userinfo'


def challenge_for(verifier):
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')


def new_verifier():
    return secrets.token_urlsafe(48)


class GoogleOAuthProvider:
    name = 'google'

    def __init__(self, client_id, client_secret, timeout=15):
        self.client_id, self.client_secret, self.timeout = client_id, client_secret, timeout

    @classmethod
    def from_environment(cls):
        client_id = (os.environ.get('GOOGLE_CLIENT_ID') or '').strip()
        client_secret = (os.environ.get('GOOGLE_CLIENT_SECRET') or '').strip()
        return cls(client_id, client_secret) if client_id and client_secret else None

    def authorization_url(self, state, verifier, redirect_uri):
        query = urllib.parse.urlencode({
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid email profile',
            'state': state,
            'code_challenge': challenge_for(verifier),
            'code_challenge_method': 'S256',
            # Keeps the account chooser honest when several people share a machine.
            'prompt': 'select_account',
        })
        return f'{AUTHORIZATION_ENDPOINT}?{query}'

    def _post(self, url, payload):
        body = urllib.parse.urlencode(payload).encode('utf-8')
        request = urllib.request.Request(url, data=body, method='POST', headers={
            'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read())

    def _userinfo(self, access_token):
        request = urllib.request.Request(USERINFO_ENDPOINT, headers={
            'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read())

    def exchange(self, code, verifier, redirect_uri):
        try:
            tokens = self._post(TOKEN_ENDPOINT, {
                'code': code,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
                'code_verifier': verifier,
            })
            claims = self._userinfo(tokens['access_token'])
        except (OSError, KeyError, ValueError) as exc:
            raise AuthError('Não foi possível concluir o login com o Google') from exc
        email = (claims.get('email') or '').strip()
        if not email:
            raise AuthError('O Google não informou um e-mail')
        return OAuthProfile(
            provider=self.name,
            subject=str(claims.get('sub') or ''),
            email=email,
            # Never trusted implicitly: an unverified address would let anyone register
            # someone else's e-mail at the provider and inherit their account here.
            email_verified=bool(claims.get('email_verified')),
            name=(claims.get('name') or '').strip(),
            raw=claims,
        )
