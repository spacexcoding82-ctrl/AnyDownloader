"""Public-network-only transport for isolated yt-dlp workers.

DNS validation alone is insufficient: socket connection targets are checked too,
including redirect, manifest, fragment and DNS-rebinding destinations.
"""
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit


class MediaError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split('%')[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        # Translation/tunnel addresses can route to forbidden IPv4 destinations.
        if isinstance(address, ipaddress.IPv6Address) and (
            address in ipaddress.ip_network('64:ff9b::/96')
            or address in ipaddress.ip_network('64:ff9b:1::/48')
            or address.sixtofour or address.teredo
        ):
            return False
        return address.is_global and not address.is_multicast
    except ValueError:
        return False


def validate_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        if (parts.scheme not in ('https', 'http') or not parts.hostname
                or parts.username or parts.password or parts.port not in (None, 80, 443)
                or len(value) > 2048 or any(ord(c) < 33 for c in value.strip())
                or '\\' in value):
            raise ValueError()
        host = parts.hostname.lower().rstrip('.')
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if '.' not in host:
                raise ValueError()
        else:
            if not public_ip(host):
                raise ValueError()
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))
    except ValueError:
        raise MediaError('invalid_url', 'Paste a public http or https video link.') from None


def install_network_guard():
    """Called only in a short-lived child process, never in the API server."""
    original_resolve = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def resolve(host, port, *args, **kwargs):
        results = original_resolve(host, port, *args, **kwargs)
        if not results or any(not public_ip(item[4][0]) for item in results):
            raise OSError('Private or reserved network destination blocked')
        return results

    def checked_address(sock, address):
        if sock.family not in (socket.AF_INET, socket.AF_INET6):
            raise OSError('Only public internet connections are allowed')
        if address[1] not in (80, 443):
            raise OSError('Destination port blocked')
        # Resolve once and connect to the validated numeric result (no second DNS lookup).
        entries = resolve(address[0], address[1], sock.family, sock.type)
        return entries[0][4]

    def connect(sock, address):
        return original_connect(sock, checked_address(sock, address))

    def connect_ex(sock, address):
        return original_connect_ex(sock, checked_address(sock, address))

    socket.getaddrinfo = resolve
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
