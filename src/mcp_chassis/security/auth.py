"""Authentication and authorization framework for the MCP Chassis server.

Provides a pluggable AuthProvider ABC with two built-in implementations:
- NoAuthProvider: always authenticates (for stdio/trusted environments)
- TokenAuthProvider: simple bearer token comparison (for future HTTP use)
"""

from __future__ import annotations

import hmac
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from mcp_chassis.errors import AuthError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthIdentity:
    """Represents an authenticated caller.

    Attributes:
        id: Unique identifier for the caller.
        scopes: Set of authorized scopes granted to this identity.
    """

    id: str
    scopes: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class AuthResult:
    """Result of an authentication attempt.

    Attributes:
        authenticated: Whether authentication succeeded.
        identity: The authenticated identity (None if failed).
        reason: Human-readable reason for failure (empty if succeeded).
    """

    authenticated: bool
    identity: AuthIdentity | None = None
    reason: str = ""

    @classmethod
    def success(cls, identity: AuthIdentity) -> AuthResult:
        """Create a successful auth result.

        Args:
            identity: The authenticated identity.

        Returns:
            AuthResult with authenticated=True.
        """
        return cls(authenticated=True, identity=identity)

    @classmethod
    def failure(cls, reason: str) -> AuthResult:
        """Create a failed auth result.

        Args:
            reason: Human-readable reason for failure.

        Returns:
            AuthResult with authenticated=False.
        """
        return cls(authenticated=False, identity=None, reason=reason)


class AuthProvider(ABC):
    """Abstract base class for authentication providers.

    Implement this class to provide custom authentication logic.
    All methods are async to support I/O-bound auth backends.
    """

    @abstractmethod
    async def authenticate(self, request_context: dict[str, Any]) -> AuthResult:
        """Authenticate an incoming request.

        Args:
            request_context: Dict containing request metadata (headers,
                transport info, etc.). Contents depend on transport type.

        Returns:
            AuthResult indicating success or failure.
        """

    @abstractmethod
    async def authorize(
        self, identity: AuthIdentity, tool_name: str, scopes: list[str]
    ) -> bool:
        """Check if an identity is authorized to call a tool with given scopes.

        Args:
            identity: The authenticated identity.
            tool_name: Name of the tool being invoked.
            scopes: Required scopes for the tool.

        Returns:
            True if authorized; False otherwise.
        """


class NoAuthProvider(AuthProvider):
    """No-op authentication provider for stdio/trusted environments.

    Always returns authenticated=True with a local identity that has
    all scopes. Suitable for local stdio usage where the transport
    itself provides security.
    """

    async def authenticate(self, request_context: dict[str, Any]) -> AuthResult:
        """Authenticate — always succeeds with a local identity.

        Args:
            request_context: Ignored.

        Returns:
            Successful AuthResult with identity id='local'.
        """
        return AuthResult.success(AuthIdentity(id="local", scopes=frozenset(["*"])))

    async def authorize(
        self, identity: AuthIdentity, tool_name: str, scopes: list[str]
    ) -> bool:
        """Authorize — always grants access.

        Args:
            identity: The authenticated identity (ignored).
            tool_name: Tool name (ignored).
            scopes: Required scopes (ignored).

        Returns:
            Always True.
        """
        return True


class TokenAuthProvider(AuthProvider):
    """Simple bearer token authentication provider.

    Compares the token in the request context against a configured secret
    using constant-time comparison to prevent timing attacks.

    Designed for future HTTP transport use where a bearer token is
    extracted from the Authorization header.

    Args:
        token: The expected secret token.
    """

    def __init__(self, token: str) -> None:
        """Initialize with the expected token.

        Args:
            token: The secret token to authenticate against.
        """
        self._token = token

    async def authenticate(self, request_context: dict[str, Any]) -> AuthResult:
        """Authenticate by comparing the provided token.

        The request_context must contain a 'token' key with the bearer token.

        Args:
            request_context: Dict with 'token' key.

        Returns:
            AuthResult indicating success or failure.
        """
        provided = request_context.get("token", "")
        if not self._token:
            logger.error("TokenAuthProvider has no token configured")
            return AuthResult.failure("Server misconfiguration: no token configured")

        # Use constant-time comparison to prevent timing attacks
        if not provided:
            return AuthResult.failure("Authentication required: no token provided")

        match = hmac.compare_digest(
            provided.encode("utf-8"),
            self._token.encode("utf-8"),
        )
        if match:
            return AuthResult.success(
                AuthIdentity(id="token-user", scopes=frozenset(["*"]))
            )
        return AuthResult.failure("Authentication failed: invalid token")

    async def authorize(
        self, identity: AuthIdentity, tool_name: str, scopes: list[str]
    ) -> bool:
        """Authorize based on wildcard scope or explicit scope match.

        Args:
            identity: The authenticated identity.
            tool_name: Tool being invoked.
            scopes: Required scopes.

        Returns:
            True if identity has '*' scope or all required scopes.
        """
        if "*" in identity.scopes:
            return True
        return all(s in identity.scopes for s in scopes)


def create_auth_provider(provider_type: str, token: str = "") -> AuthProvider:
    """Factory function to create an AuthProvider by type name.

    Args:
        provider_type: Type name ('none', 'token').
        token: Token for TokenAuthProvider (ignored for 'none').

    Returns:
        An AuthProvider instance.

    Raises:
        AuthError: If the provider type is unknown.
    """
    if provider_type == "none":
        return NoAuthProvider()
    elif provider_type == "token":
        return TokenAuthProvider(token)
    else:
        raise AuthError(
            f"Unknown auth provider type '{provider_type}'",
            code="UNKNOWN_AUTH_PROVIDER",
        )


async def check_auth(
    provider: AuthProvider,
    request_context: dict[str, Any],
    tool_name: str,
    required_scopes: list[str],
) -> AuthIdentity:
    """Run full auth check (authenticate + authorize) and raise on failure.

    Convenience function for use in middleware.

    Args:
        provider: The AuthProvider to use.
        request_context: Request metadata for authentication.
        tool_name: Tool name for authorization check.
        required_scopes: Scopes required to call the tool.

    Returns:
        The authenticated and authorized AuthIdentity.

    Raises:
        AuthError: If authentication or authorization fails.
    """
    result = await provider.authenticate(request_context)
    if not result.authenticated or result.identity is None:
        raise AuthError(f"Authentication failed: {result.reason}")

    authorized = await provider.authorize(result.identity, tool_name, required_scopes)
    if not authorized:
        raise AuthError(
            f"Authorization failed: identity '{result.identity.id}' "
            f"lacks required scopes for tool '{tool_name}'"
        )

    return result.identity
