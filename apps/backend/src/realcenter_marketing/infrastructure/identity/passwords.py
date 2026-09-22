"""Password hashing with the standard library only.

scrypt is memory-hard on purpose, which is also why it is a lever against the server: at
n=2**14 every check costs about 16 MB, so concurrent logins must stay rate limited. The
cost parameters travel inside the encoded hash, so they can be raised later and old
hashes keep verifying until their owner next signs in.
"""
import base64
import hashlib
import hmac
import os
import threading

SCHEME = 'scrypt'
DEFAULT_N, DEFAULT_R, DEFAULT_P, DKLEN = 2 ** 14, 8, 1, 32
# hashlib.scrypt refuses to allocate past maxmem, and its default is far below what
# these parameters need. 128 * r * n is the working set; double it for headroom.
MAXMEM = 128 * DEFAULT_R * DEFAULT_N * 2


def _b64(raw):
    return base64.b64encode(raw).decode('ascii')


class ScryptHasher:
    def __init__(self, n=DEFAULT_N, r=DEFAULT_R, p=DEFAULT_P, concurrency=3):
        self.n, self.r, self.p = n, r, p
        # Without this bound, a burst of logins multiplies 16 MB by the number of
        # connection threads, which is a memory exhaustion lever rather than a slowdown.
        self._slots = threading.Semaphore(concurrency)

    def _derive(self, password, salt, n, r, p):
        with self._slots:
            return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=n, r=r, p=p,
                                  dklen=DKLEN, maxmem=128 * r * n * 2)

    def hash(self, password):
        salt = os.urandom(16)
        derived = self._derive(password, salt, self.n, self.r, self.p)
        return f'{SCHEME}${self.n}${self.r}${self.p}${_b64(salt)}${_b64(derived)}'

    def verify(self, password, encoded):
        try:
            scheme, n, r, p, salt, expected = encoded.split('$')
            if scheme != SCHEME:
                return False
            derived = self._derive(password, base64.b64decode(salt), int(n), int(r), int(p))
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(_b64(derived), expected)

    def dummy_verify(self):
        """Burn the same work for an address that has no account, so response time does
        not disclose which e-mails are registered."""
        self._derive('senha-inexistente', b'0' * 16, self.n, self.r, self.p)

    def needs_rehash(self, encoded):
        try:
            scheme, n, r, p, _, _ = encoded.split('$')
        except ValueError:
            return True
        return scheme != SCHEME or (int(n), int(r), int(p)) != (self.n, self.r, self.p)
