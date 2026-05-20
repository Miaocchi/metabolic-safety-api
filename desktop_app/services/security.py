"""URL / path policy helpers and input validation for the desktop app.

All functions in this module are pure (or near-pure) and independently
testable.  They enforce SSRF / path-traversal / resource-burn guards used
by the HTTP handler and background sync jobs.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

from desktop_app.config import ACTIVE_DB_POINTER, BUILD, SEED_DB

__all__ = [
    "ALLOWED_DOWNLOAD_HOSTS",
    "DEFAULT_MAX_DOWNLOAD_BYTES",
    "_int_param",
    "active_seed_db",
    "clean_faers_query_term",
    "looks_like_public_api_term",
    "safe_filename",
    "split_candidate_terms",
    "stable_text_hash",
    "validate_download_url",
    "validate_path_within_base",
]


# -- query-parameter helpers ------------------------------------------------

def _int_param(params: dict[str, list[str]], key: str, default: int) -> int:
    """Extract an integer query-parameter with a safe fallback.

    Returns *default* when the key is missing, the value list is empty,
    or the value cannot be parsed as an integer.
    """
    values = params.get(key)
    if not values:
        return default
    try:
        return int(values[0])
    except (TypeError, ValueError):
        return default


# -- filesystem path guards -------------------------------------------------

def active_seed_db() -> Path:
    """Return the active SQLite seed database, validated to stay within BUILD.

    If ``ACTIVE_DB_POINTER`` contains a relative filename whose resolved
    path remains inside ``BUILD``, that file is used.  Otherwise the default
    ``SEED_DB`` is returned.
    """
    if ACTIVE_DB_POINTER.exists():
        name = ACTIVE_DB_POINTER.read_text(encoding="utf-8").strip()
        candidate = BUILD / name
        if candidate.exists() and candidate.parent == BUILD:
            return candidate
    return SEED_DB


def validate_path_within_base(target: Path, base: Path) -> Path:
    """Resolve *target* and verify it is a descendant of *base*.

    Returns the resolved path on success.  Raises :class:`ValueError` if
    the resolved path escapes *base* (path-traversal guard).
    """
    resolved = target.resolve()
    base_resolved = base.resolve()
    resolved.relative_to(base_resolved)
    return resolved


# -- filename sanitisation --------------------------------------------------

def safe_filename(value: str) -> str:
    """Sanitise a URL or raw string into a safe local filename.

    Extracts the last path component of a URL, strips unsafe characters,
    and returns a non-empty safe name (falling back to ``"download.bin"``).
    """
    name = Path(urlparse(value).path).name if "/" in value else value
    name = re.sub(r"[^A-Za-z0-9._+\-()\[\] ]+", "_", name).strip(" .")
    return name or "download.bin"


# -- public-API term validation ---------------------------------------------

def looks_like_public_api_term(term: str) -> bool:
    """Return *True* if *term* looks like a reasonable drug-name query."""
    if not re.search(r"[A-Za-z]", term):
        return False
    if len(term) < 2 or len(term) > 80:
        return False
    if term[0].isdigit():
        return False
    if re.search(r"[{}\[\]\\]", term):
        return False
    if term.count(" ") > 5:
        return False
    noisy_words = (
        " oral ", " tablet", " capsule", " pack", " kit",
        " injection", " solution",
    )
    lowered = f" {term.lower()} "
    return not any(word in lowered for word in noisy_words)


# -- FAERS query-term sanitisation ------------------------------------------

def clean_faers_query_term(value: object) -> str:
    """Normalise a raw value into a FAERS-safe query term.

    Strips dosage forms, strength annotations, brackets, and rejects terms
    that contain digits, are too short/long, or contain suspicious chars.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\[[^\]]+\]|[{}]", " ", text)
    text = re.sub(
        r"\b\d+(?:\.\d+)?\s*(?:MG|MCG|UG|G|ML|%)\b",
        " ", text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?:ORAL|TABLET|TABLETS|CAPSULE|CAPSULES|SOLUTION|TOPICAL|"
        r"LOTION|PACK|KIT|SPRAY|INJECTION|EXTENDED|RELEASE|DELAYED|"
        r"CHEWABLE|FILM|COATED|LIQUID|SYRUP|SUSPENSION)\b",
        " ", text, flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip(" -/,()")
    if not re.search(r"[A-Za-z]", text):
        return ""
    if re.search(r"\d", text):
        return ""
    if any(marker in text for marker in ("/", "{", "}")):
        return ""
    if len(text) < 3 or len(text) > 60:
        return ""
    return text


def split_candidate_terms(value: object) -> list[str]:
    """Split a value on `` / `` and ``|`` into individual candidate terms."""
    if value is None:
        return []
    text = str(value).replace("_", " ").strip()
    if not text:
        return []
    parts = [text]
    if " / " in text:
        parts.extend(part.strip() for part in text.split(" / "))
    if "|" in text:
        parts.extend(part.strip() for part in text.split("|"))
    return parts


# -- hashing ----------------------------------------------------------------

def stable_text_hash(value: str) -> str:
    """Return the first 12 hex chars of the SHA-256 of *value*."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


# -- Network / download URL validation --------------------------------------

#: Hostnames that are permitted as download targets.  The list covers every
#: host that the bundled source adapters and manifest fetchers contact.
ALLOWED_DOWNLOAD_HOSTS: frozenset[str] = frozenset({
    # openFDA
    "api.fda.gov",
    "download.open.fda.gov",
    # DailyMed
    "dailymed.nlm.nih.gov",
    "dailymed-data.nlm.nih.gov",
    # ChEMBL / EBI
    "ftp.ebi.ac.uk",
    "www.ebi.ac.uk",
    # GitHub (releases, archives)
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    # Zenodo
    "zenodo.org",
    # RxNav
    "rxnav.nlm.nih.gov",
    # PharmGKB
    "api.pharmgkb.org",
    "www.pharmgkb.org",
})

#: Default cap for streamed downloads (4 GiB).  Callers may override.
DEFAULT_MAX_DOWNLOAD_BYTES: int = 4 * 1024 * 1024 * 1024


def validate_download_url(
    url: str,
    *,
    allowed_hosts: frozenset[str] | None = None,
) -> None:
    """Validate a download URL against SSRF / resource-burn policy.

    Checks performed:
    1. Scheme must be ``https`` (``http`` only for loopback).
    2. Hostname must be in *allowed_hosts* (defaults to
       :data:`ALLOWED_DOWNLOAD_HOSTS`).
    3. If the hostname is an IP literal, it must not be loopback,
       private, link-local, reserved, or the cloud-metadata endpoint.
    4. If the hostname resolves, none of the resolved IPs may be
       loopback / private / link-local / reserved (best-effort; DNS
       failures are tolerated to avoid excessive fragility).

    Raises :class:`ValueError` on policy violation.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port

    # -- scheme gate ----------------------------------------------------------
    if scheme == "http":
        # Allow http only for loopback hostnames.
        if hostname not in ("127.0.0.1", "localhost", "::1", "[::1]"):
            raise ValueError(f"HTTP scheme only allowed for loopback, got: {hostname}")
    elif scheme != "https":
        raise ValueError(f"Unsupported URL scheme: {scheme!r}")

    if not hostname:
        raise ValueError("URL has no hostname")

    # -- hostname allow-list --------------------------------------------------
    hosts = allowed_hosts if allowed_hosts is not None else ALLOWED_DOWNLOAD_HOSTS
    if hostname not in hosts and not any(hostname.endswith("." + h) for h in hosts):
        raise ValueError(f"Hostname not in allowed set: {hostname}")

    # -- IP-literal guard (no DNS needed) -------------------------------------
    _check_ip_literal(hostname)

    # -- resolved-IP guard (best-effort) --------------------------------------
    _check_resolved_ips(hostname, port or (443 if scheme == "https" else 80))


def _check_ip_literal(hostname: str) -> None:
    """If *hostname* is an IP literal, reject private / reserved ranges."""
    # Strip IPv6 brackets
    raw = hostname.strip("[]")
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return  # not an IP literal — nothing to check here
    _assert_public_ip(ip, hostname)


def _check_resolved_ips(hostname: str, port: int) -> None:
    """Best-effort: resolve *hostname* and reject private IPs."""
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        return  # DNS failure is tolerated
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        _assert_public_ip(ip, hostname)


def _assert_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, label: str) -> None:
    """Raise if *ip* is loopback / private / link-local / reserved / metadata."""
    if ip.is_loopback:
        raise ValueError(f"URL {label} resolves to loopback IP: {ip}")
    if ip.is_private:
        raise ValueError(f"URL {label} resolves to private IP: {ip}")
    if ip.is_link_local:
        raise ValueError(f"URL {label} resolves to link-local IP: {ip}")
    if ip.is_reserved:
        raise ValueError(f"URL {label} resolves to reserved IP: {ip}")
    # Explicitly block the AWS / cloud metadata endpoint (169.254.169.254).
    if isinstance(ip, ipaddress.IPv4Address) and str(ip) == "169.254.169.254":
        raise ValueError(f"URL {label} resolves to cloud metadata endpoint: {ip}")
