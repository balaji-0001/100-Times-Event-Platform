"""SSRF Protection and URL Safety Validation.

Validates that outbound HTTP requests and user-supplied URLs cannot target
private networks, internal loopback, link-local addresses, cloud metadata services,
or non-HTTP/HTTPS schemes.
"""

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
}


def is_safe_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return not (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return False


def validate_safe_url(url: str, allow_private_in_dev: bool = False) -> str:
    """Validates that a URL is well-formed, uses http/https, and does not resolve

    to an internal, private, loopback, or cloud-metadata network address.
    Raises ValueError if the URL is unsafe or invalid.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string.")

    cleaned = url.strip()
    parsed = urlparse(cleaned)

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme '{parsed.scheme}'. Only http and https are permitted.")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("URL must contain a valid hostname.")

    if not allow_private_in_dev and hostname in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Access to restricted hostname '{hostname}' is blocked.")

    # In dev/test environments, permit RFC 2606 reserved test domains used in unit tests
    if allow_private_in_dev and hostname.endswith((".test", ".example", ".invalid")):
        return cleaned

    # Check literal IP in hostname
    try:
        ip = ipaddress.ip_address(hostname)
        if not is_safe_ip(str(ip)) and not allow_private_in_dev:
            raise ValueError(f"Access to private/restricted IP address '{hostname}' is blocked.")
        return cleaned
    except ValueError:
        pass  # It's a domain name, proceed to DNS resolution

    # DNS resolution check
    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        resolved_ips = {item[4][0] for item in addr_info}
    except socket.gaierror as exc:
        if allow_private_in_dev:
            return cleaned
        raise ValueError(f"Could not resolve hostname '{hostname}': {exc}") from exc

    if not resolved_ips:
        raise ValueError(f"No IP addresses resolved for hostname '{hostname}'.")

    if not allow_private_in_dev:
        for ip_addr in resolved_ips:
            if not is_safe_ip(ip_addr):
                raise ValueError(
                    f"Access to hostname '{hostname}' is blocked because it resolves to private/restricted IP '{ip_addr}'."
                )

    return cleaned

