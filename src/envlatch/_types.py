"""Local syntax checks; values never leave these predicates or reach diagnostics."""

from __future__ import annotations

import ipaddress
import re

TYPE_NAMES = ("string", "integer", "boolean", "url", "port")
_INTEGER = re.compile(r"[+-]?[0-9]+\Z")
_DIGITS = re.compile(r"[0-9]+\Z")
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://([^/?#]*)(?:[/?#].*)?\Z")
_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")
_BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_USERINFO = re.compile(r"[A-Za-z0-9._~!$&'()*+,;=:%-]*\Z")


def _port(value: str) -> bool:
    if not _DIGITS.fullmatch(value):
        return False
    # Avoid integer-conversion limits even for unusually long input.
    number = value.lstrip("0")
    return bool(number) and (len(number) < 5 or (len(number) == 5 and number <= "65535"))


def _url(value: str) -> bool:
    if _BAD_PERCENT.search(value) or any(
        char.isspace() or ord(char) < 32 or 127 <= ord(char) <= 159 or char in '\\<>"{}|^`'
        for char in value
    ):
        return False
    match = _URL.fullmatch(value)
    if match is None:
        return False
    try:
        # Parse locally rather than using a URL parser that caches raw inputs.
        netloc = match[1]
        authority = netloc.rsplit("@", 1)[-1]
        if netloc.count("@") > 1 or not authority:
            return False
        if "@" in netloc and not _USERINFO.fullmatch(netloc.rsplit("@", 1)[0]):
            return False
        if authority.startswith("["):
            end = authority.index("]")
            # Require bracketed IPv6 and a well-formed optional port suffix.
            ipaddress.IPv6Address(authority[1:end])
            suffix = authority[end + 1 :]
            return not suffix or (suffix.startswith(":") and _port(suffix[1:]))
        if "[" in authority or "]" in authority or authority.count(":") > 1:
            return False
        host, separator, port = authority.partition(":")
        if separator and not _port(port):
            return False
        host = host.encode("idna").decode("ascii").removesuffix(".")
        if not host or len(host) > 253:
            return False
        if re.fullmatch(r"[0-9.]+", host) and "." in host:
            ipaddress.IPv4Address(host)
        return all(_LABEL.fullmatch(label) for label in host.split("."))
    except (ValueError, UnicodeError):
        # IDNA/IP exceptions may contain input: never expose their messages.
        return False


def matches_type(value: str, kind: str) -> bool:
    """Check the literal dotenv value, without coercion or network access."""
    if kind == "string":
        return True
    if kind == "integer":
        return _INTEGER.fullmatch(value) is not None
    if kind == "boolean":
        return value.lower() in ("true", "false", "1", "0")
    if kind == "port":
        return _port(value)
    return kind == "url" and _url(value)
