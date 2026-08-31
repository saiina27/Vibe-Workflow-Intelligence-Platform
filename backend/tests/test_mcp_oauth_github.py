from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.mcp.oauth.github import GitHubOAuthProvider


def test_github_provider_name():
    provider = GitHubOAuthProvider()

    assert provider.name == "github"


def test_github_authorization_url():
    provider = GitHubOAuthProvider()

    with patch(
        "app.mcp.oauth.github.settings.github_client_id",
        "github-client-id",
    ), patch(
        "app.mcp.oauth.github.settings.github_client_secret",
        "github-client-secret",
    ), patch(
        "app.mcp.oauth.github.settings.github_redirect_uri",
        "http://localhost:8000/integrations/github/callback",
    ), patch(
        "app.mcp.oauth.github.settings.github_oauth_scope",
        "read:user",
    ):
        url = provider.get_authorization_url(
            "test-state"
        )

    assert (
        "https://github.com/login/oauth/authorize?"
        in url
    )
    assert "client_id=github-client-id" in url
    assert "state=test-state" in url
    assert "scope=read%3Auser" in url


def test_empty_state_is_rejected():
    provider = GitHubOAuthProvider()

    with pytest.raises(
        ValueError,
        match="state cannot be empty",
    ):
        provider.get_authorization_url("")


@pytest.mark.asyncio
async def test_exchange_code():
    provider = GitHubOAuthProvider()

    response = httpx.Response(
        200,
        json={
            "access_token": "gho_test",
            "scope": "read:user",
        },
        request=httpx.Request(
            "POST",
            provider.TOKEN_URL,
        ),
    )

    with patch(
        "app.mcp.oauth.github.settings.github_client_id",
        "client-id",
    ), patch(
        "app.mcp.oauth.github.settings.github_client_secret",
        "client-secret",
    ), patch(
        "app.mcp.oauth.github.settings.github_redirect_uri",
        "http://localhost/callback",
    ), patch(
        "app.mcp.oauth.github.httpx.AsyncClient",
    ) as client_class:

        client = client_class.return_value.__aenter__.return_value

        client.post = AsyncMock(
            return_value=response
        )

        token = await provider.exchange_code(
            "authorization-code"
        )

    assert token.access_token == "gho_test"
    assert token.scope == "read:user"


@pytest.mark.asyncio
async def test_get_user():
    provider = GitHubOAuthProvider()

    response = httpx.Response(
        200,
        json={
            "id": 12345,
            "login": "octocat",
        },
        request=httpx.Request(
            "GET",
            provider.USER_URL,
        ),
    )

    with patch(
        "app.mcp.oauth.github.httpx.AsyncClient",
    ) as client_class:

        client = client_class.return_value.__aenter__.return_value

        client.get = AsyncMock(
            return_value=response
        )

        user = await provider.get_user(
            "gho_test"
        )

    assert user["id"] == 12345
    assert user["login"] == "octocat"