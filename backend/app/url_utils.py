"""URL cleaning for feed data.

The iOS app can only use http(s) article links, and App Transport Security blocks plain-http
images in Release builds. Links in feeds are untrusted, so anything unusable becomes None here.
"""

import hashlib
import ipaddress
import socket
from urllib.parse import quote, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_", "at_")
_TRACKING_PARAMS = {
    "cmp", "ex_cid", "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ocid", "publisher",
    "traffic_source",
}
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _is_tracking(pair: str) -> bool:
    key = pair.split("=", 1)[0].lower()
    return key in _TRACKING_PARAMS or key.startswith(_TRACKING_PREFIXES)


def _clean(raw: str | None, *, strip_tracking: bool) -> str | None:
    if not raw or not raw.strip():
        return None
    try:
        parts = urlsplit(raw.strip())
        host = parts.hostname
        port = parts.port
        if parts.scheme.lower() not in _DEFAULT_PORTS or not host or parts.username or parts.password:
            return None
        host = host.encode("idna").decode("ascii").lower()
    except (ValueError, UnicodeError):
        return None

    netloc = f"[{host}]" if ":" in host else host
    if port and port != _DEFAULT_PORTS[parts.scheme.lower()]:
        netloc += f":{port}"

    # Existing %XX escapes are kept; spaces and non-ASCII characters get encoded.
    path = quote(parts.path, safe="/%:@!$&'()*+,;=~-._")
    query = quote(parts.query, safe="/%:@!$&'()*+,;=~-._?")
    if strip_tracking:
        query = "&".join(p for p in query.split("&") if p and not _is_tracking(p))
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def clean_article_url(raw: str | None) -> str | None:
    """A usable http(s) link with tracking parameters and the fragment removed, or None."""
    return _clean(raw, strip_tracking=True)


def clean_image_url(raw: str | None) -> str | None:
    """An https image link, or None. The query is untouched, since image CDNs often sign it."""
    url = _clean(raw, strip_tracking=False)
    if url is None:
        return None
    return "https://" + url.removeprefix("http://").removeprefix("https://")


def normalise_url(url: str) -> str:
    """The form used for article IDs, so trivial variations of a link map to the same article."""
    parts = urlsplit(url)
    pairs = sorted(p for p in parts.query.split("&") if p)
    return urlunsplit(("https", parts.netloc.lower(), parts.path.rstrip("/"), "&".join(pairs), ""))


def article_id(url: str) -> str:
    return hashlib.sha256(normalise_url(url).encode()).hexdigest()[:16]


def is_public_url(url: str) -> bool:
    """False for hosts on private or local networks, so a malicious feed link can't make the
    server probe its own infrastructure."""
    host = urlsplit(url).hostname
    if not host:
        return False
    try:
        addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    return bool(addresses) and all(
        ipaddress.ip_address(info[4][0].split("%")[0]).is_global for info in addresses
    )
