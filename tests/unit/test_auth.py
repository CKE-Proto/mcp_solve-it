"""Unit tests for mcp_chassis.security.auth module."""

import pytest

from mcp_chassis.errors import AuthError
from mcp_chassis.security.auth import (
    AuthIdentity,
    AuthProvider,
    AuthResult,
    NoAuthProvider,
    TokenAuthProvider,
    check_auth,
    create_auth_provider,
)


class TestAuthIdentity:
    """Tests for AuthIdentity dataclass."""

    def test_basic_identity(self) -> None:
        identity = AuthIdentity(id="user1")
        assert identity.id == "user1"
        assert identity.scopes == frozenset()

    def test_identity_with_scopes(self) -> None:
        identity = AuthIdentity(id="admin", scopes=frozenset(["read", "write"]))
        assert "read" in identity.scopes
        assert "write" in identity.scopes

    def test_identity_is_frozen(self) -> None:
        identity = AuthIdentity(id="user")
        with pytest.raises((AttributeError, TypeError)):
            identity.id = "changed"  # type: ignore[misc]


class TestAuthResult:
    """Tests for AuthResult dataclass."""

    def test_success_result(self) -> None:
        identity = AuthIdentity(id="user")
        result = AuthResult.success(identity)
        assert result.authenticated
        assert result.identity == identity
        assert result.reason == ""

    def test_failure_result(self) -> None:
        result = AuthResult.failure("bad token")
        assert not result.authenticated
        assert result.identity is None
        assert result.reason == "bad token"


class TestNoAuthProvider:
    """Tests for NoAuthProvider."""

    @pytest.mark.asyncio
    async def test_authenticate_always_succeeds(self) -> None:
        provider = NoAuthProvider()
        result = await provider.authenticate({})
        assert result.authenticated

    @pytest.mark.asyncio
    async def test_authenticate_returns_local_identity(self) -> None:
        provider = NoAuthProvider()
        result = await provider.authenticate({"some": "context"})
        assert result.identity is not None
        assert result.identity.id == "local"

    @pytest.mark.asyncio
    async def test_authenticate_grants_wildcard_scope(self) -> None:
        provider = NoAuthProvider()
        result = await provider.authenticate({})
        assert result.identity is not None
        assert "*" in result.identity.scopes

    @pytest.mark.asyncio
    async def test_authorize_always_true(self) -> None:
        provider = NoAuthProvider()
        identity = AuthIdentity(id="local", scopes=frozenset(["*"]))
        assert await provider.authorize(identity, "any_tool", ["any_scope"])

    @pytest.mark.asyncio
    async def test_is_auth_provider(self) -> None:
        provider = NoAuthProvider()
        assert isinstance(provider, AuthProvider)


class TestTokenAuthProvider:
    """Tests for TokenAuthProvider."""

    @pytest.mark.asyncio
    async def test_valid_token_authenticates(self) -> None:
        provider = TokenAuthProvider("secret-token")
        result = await provider.authenticate({"token": "secret-token"})
        assert result.authenticated

    @pytest.mark.asyncio
    async def test_invalid_token_fails(self) -> None:
        provider = TokenAuthProvider("secret-token")
        result = await provider.authenticate({"token": "wrong-token"})
        assert not result.authenticated

    @pytest.mark.asyncio
    async def test_missing_token_fails(self) -> None:
        provider = TokenAuthProvider("secret-token")
        result = await provider.authenticate({})
        assert not result.authenticated

    @pytest.mark.asyncio
    async def test_empty_provider_token_fails(self) -> None:
        # Provider configured with empty token — server misconfiguration
        provider = TokenAuthProvider("")
        result = await provider.authenticate({"token": "anything"})
        assert not result.authenticated

    @pytest.mark.asyncio
    async def test_successful_auth_returns_identity(self) -> None:
        provider = TokenAuthProvider("my-token")
        result = await provider.authenticate({"token": "my-token"})
        assert result.identity is not None
        assert result.identity.id == "token-user"

    @pytest.mark.asyncio
    async def test_authorize_with_wildcard_scope(self) -> None:
        provider = TokenAuthProvider("t")
        identity = AuthIdentity(id="u", scopes=frozenset(["*"]))
        assert await provider.authorize(identity, "tool", ["read", "write"])

    @pytest.mark.asyncio
    async def test_authorize_without_required_scope(self) -> None:
        provider = TokenAuthProvider("t")
        identity = AuthIdentity(id="u", scopes=frozenset(["read"]))
        assert not await provider.authorize(identity, "tool", ["read", "write"])

    @pytest.mark.asyncio
    async def test_authorize_with_all_required_scopes(self) -> None:
        provider = TokenAuthProvider("t")
        identity = AuthIdentity(id="u", scopes=frozenset(["read", "write"]))
        assert await provider.authorize(identity, "tool", ["read", "write"])


class TestCreateAuthProvider:
    """Tests for create_auth_provider factory function."""

    def test_creates_no_auth_provider(self) -> None:
        provider = create_auth_provider("none")
        assert isinstance(provider, NoAuthProvider)

    def test_creates_token_auth_provider(self) -> None:
        provider = create_auth_provider("token", "my-secret")
        assert isinstance(provider, TokenAuthProvider)

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(AuthError):
            create_auth_provider("oauth2")


class TestCheckAuth:
    """Tests for check_auth convenience function."""

    @pytest.mark.asyncio
    async def test_successful_auth_returns_identity(self) -> None:
        provider = NoAuthProvider()
        identity = await check_auth(provider, {}, "my_tool", [])
        assert identity.id == "local"

    @pytest.mark.asyncio
    async def test_failed_auth_raises_auth_error(self) -> None:
        provider = TokenAuthProvider("secret")
        with pytest.raises(AuthError):
            await check_auth(provider, {"token": "wrong"}, "tool", [])

    @pytest.mark.asyncio
    async def test_failed_authz_raises_auth_error(self) -> None:
        # Auth succeeds but authz fails because of missing scope
        # (token provider grants * scope on success, so we test with a custom provider)
        class RestrictedProvider(AuthProvider):
            async def authenticate(self, request_context: dict) -> AuthResult:
                return AuthResult.success(
                    AuthIdentity(id="limited", scopes=frozenset(["read"]))
                )

            async def authorize(
                self, identity: AuthIdentity, tool_name: str, scopes: list[str]
            ) -> bool:
                return False

        provider_r = RestrictedProvider()
        with pytest.raises(AuthError, match="Authorization failed"):
            await check_auth(provider_r, {}, "admin_tool", ["admin"])
