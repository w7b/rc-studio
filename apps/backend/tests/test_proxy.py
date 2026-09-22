import socket

import pytest

from realcenter_marketing.presentation.http.proxy import client_address


@pytest.mark.parametrize('forwarded', [None, '', 'not-an-ip', '203.0.113.1, 203.0.113.2', '203.0.113.1:80'])
def test_proxy_rejects_missing_malformed_and_chained_addresses(forwarded):
    assert client_address('192.0.2.1', forwarded, ('192.0.2.1',)) == '192.0.2.1'


def test_untrusted_peer_cannot_choose_its_rate_limit_identity():
    assert client_address('192.0.2.99', '203.0.113.1', ('192.0.2.1',)) == '192.0.2.99'
    assert client_address('127.0.0.1', '203.0.113.1', ()) == '127.0.0.1'


def test_proxy_follows_dns_replacement_without_trusting_the_old_address(monkeypatch):
    address = '192.0.2.1'
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs:
                        [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 0))])
    assert client_address('192.0.2.1', '203.0.113.1', ('nginx',)) == '203.0.113.1'
    address = '192.0.2.2'
    assert client_address('192.0.2.1', '203.0.113.1', ('nginx',)) == '192.0.2.1'
    assert client_address('192.0.2.2', '203.0.113.1', ('nginx',)) == '203.0.113.1'


def test_dns_failure_falls_back_to_socket_address(monkeypatch):
    def unavailable(*args, **kwargs):
        raise socket.gaierror('unavailable')
    monkeypatch.setattr(socket, 'getaddrinfo', unavailable)
    assert client_address('192.0.2.1', '203.0.113.1', ('nginx',)) == '192.0.2.1'


def test_ipv6_is_canonical_for_a_trusted_peer():
    assert client_address('::1', '2001:0db8:0:0:0:0:0:1', ('::1',)) == '2001:db8::1'
