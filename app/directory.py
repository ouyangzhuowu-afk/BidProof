"""LDAP / Active Directory authentication.

Credentials are verified by binding to the customer's directory as the user; BidProof never
stores a password for a directory-backed account. `ldap3` is an optional dependency so a
deployment that does not use a directory need not install it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class DirectoryError(RuntimeError):
    """Configuration or connection failure. Distinct from invalid credentials."""


@dataclass(frozen=True)
class DirectorySettings:
    server_uri: str
    user_dn_template: str
    base_dn: str = ""
    role_attribute: str = ""
    default_role: str = "REVIEWER"
    use_tls: bool = True

    @property
    def enabled(self) -> bool:
        return bool(self.server_uri and self.user_dn_template)


def settings_from_env() -> DirectorySettings:
    return DirectorySettings(
        server_uri=os.environ.get("BIDPROOF_LDAP_URI", "").strip(),
        # For example: uid={username},ou=people,dc=example,dc=com
        # or Active Directory style: {username}@example.com
        user_dn_template=os.environ.get("BIDPROOF_LDAP_USER_DN_TEMPLATE", "").strip(),
        base_dn=os.environ.get("BIDPROOF_LDAP_BASE_DN", "").strip(),
        role_attribute=os.environ.get("BIDPROOF_LDAP_ROLE_ATTRIBUTE", "").strip(),
        default_role=os.environ.get("BIDPROOF_LDAP_DEFAULT_ROLE", "REVIEWER").strip().upper(),
        use_tls=os.environ.get("BIDPROOF_LDAP_USE_TLS", "1").strip().lower() in {"1", "true", "yes"},
    )


def ldap_filter_escape(value: str) -> str:
    """Escape RFC 4515 special characters so a DN cannot alter a search filter."""
    return (
        value.replace("\\", "\\5c")
        .replace("*", "\\2a")
        .replace("(", "\\28")
        .replace(")", "\\29")
        .replace("\x00", "\\00")
    )


def bind_dn_for(settings: DirectorySettings, username: str) -> str:
    """Render the bind DN for a username.

    The username is placed into a configured template rather than concatenated into a filter,
    so it cannot alter the structure of the DN.
    """
    cleaned = username.strip()
    if not cleaned or any(character in cleaned for character in ",=+<>#;\\\"*()\x00"):
        raise DirectoryError("username contains characters that are not valid in a bind DN")
    return settings.user_dn_template.format(username=cleaned)


def authenticate(settings: DirectorySettings, username: str, password: str, *, connector=None) -> dict:
    """Bind as the user and return the directory attributes on success.

    Raises DirectoryError when the directory is unreachable or misconfigured; returns an empty
    mapping when the credentials are simply wrong, so callers can tell the two apart.
    """
    if not settings.enabled:
        raise DirectoryError("directory authentication is not configured")
    if not password:
        return {}
    connect = connector or _ldap3_connector
    return connect(settings, bind_dn_for(settings, username), password)


def _ldap3_connector(settings: DirectorySettings, bind_dn: str, password: str) -> dict:
    try:
        import ldap3
    except ImportError as exc:  # pragma: no cover - exercised only without the extra installed
        raise DirectoryError("ldap3 is not installed; install the 'ldap' extra to use directory login") from exc

    server = ldap3.Server(settings.server_uri, use_ssl=settings.use_tls, get_info=ldap3.NONE)
    connection = ldap3.Connection(server, user=bind_dn, password=password, raise_exceptions=False)
    if not connection.bind():
        return {}
    try:
        attributes: dict = {"dn": bind_dn}
        if settings.role_attribute and settings.base_dn:
            connection.search(
                search_base=settings.base_dn,
                search_filter=f"(distinguishedName={ldap_filter_escape(bind_dn)})",
                attributes=[settings.role_attribute],
            )
            if connection.entries:
                attributes[settings.role_attribute] = connection.entries[0][settings.role_attribute].value
        return attributes
    finally:
        connection.unbind()


def role_from_attributes(settings: DirectorySettings, attributes: dict) -> str:
    from .authz import ROLE_PERMISSIONS

    if settings.role_attribute:
        claimed = str(attributes.get(settings.role_attribute, "")).strip().upper()
        if claimed in ROLE_PERMISSIONS:
            return claimed
    return settings.default_role if settings.default_role in ROLE_PERMISSIONS else "REVIEWER"
