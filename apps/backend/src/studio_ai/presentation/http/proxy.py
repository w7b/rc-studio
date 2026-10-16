"""Client address at a deliberately configured reverse-proxy boundary."""
import ipaddress
import socket


def client_address(peer, forwarded, trusted_proxies):
    """Trust only the single X-Real-IP overwritten by the immediate proxy.

    Resolve names on each login so replacing a Docker service drops trust in its
    old IP. No wildcard, private-network or forwarded-chain trust is inferred.
    Invalid addresses and unavailable DNS fall back to the socket peer.
    """
    try:
        original = ipaddress.ip_address(peer)
        client = ipaddress.ip_address(forwarded or '')
    except ValueError:
        return peer
    for proxy in trusted_proxies:
        try:
            addresses = [ipaddress.ip_address(proxy)]
        except ValueError:
            try:
                addresses = [ipaddress.ip_address(item[4][0])
                             for item in socket.getaddrinfo(proxy, None, type=socket.SOCK_STREAM)]
            except (OSError, ValueError):
                continue
        if original in addresses:
            return str(client)
    return peer
