
from __future__ import annotations

import hashlib
import base64
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.mcp.oauth.base import OAuthProvider, OAuthToken


class SlackOAuthProvider(OAuthProvider):
    """
    Slack MCP OAuth implementation.

    Uses Slack's MCP-specific OAuth endpoints:

        Authorization:
            https://slack.com/oauth/v2_user/authorize

        Token:
            https://slack.com/api/oauth.v2.user.access

    The flow uses PKCE with S256.
    """

    AUTHORIZE_URL = (
    "https://slack.com/oauth/v2_user/authorize"
    )

    TOKEN_URL = (
    "https://slack.com/api/oauth.v2.user.access"
    )

    USER_URL = (
        "https://slack.com/api/auth.test"
    )

    @property
    def name(self) -> str:
        return "slack"

    # ========================================================
    # CONFIG
    # ========================================================

    def _require_config(self) -> None:
        if not settings.slack_client_id:
            raise RuntimeError(
                "Slack OAuth client ID is not configured."
            )

        if not settings.slack_client_secret:
            raise RuntimeError(
                "Slack OAuth client secret is not configured."
            )

        if not settings.slack_redirect_uri:
            raise RuntimeError(
                "Slack OAuth redirect URI is not configured."
            )

    # ========================================================
    # PKCE
    # ========================================================

    def generate_code_verifier(self) -> str:
        """
        Generate a PKCE code verifier.
        """

        return secrets.token_urlsafe(64)

    def generate_code_challenge(
        self,
        code_verifier: str,
    ) -> str:
        """
        Generate an S256 PKCE code challenge.
        """

        if not code_verifier:
            raise ValueError(
                "PKCE code verifier cannot be empty."
            )

        digest = hashlib.sha256(
            code_verifier.encode("ascii")
        ).digest()

        return (
            base64.urlsafe_b64encode(digest)
            .rstrip(b"=")
            .decode("ascii")
        )

    # ========================================================
    # AUTHORIZATION URL
    # ========================================================

    def get_authorization_url(
        self,
        state: str,
        code_challenge: str | None = None,
    ) -> str:
        """
        Build Slack MCP OAuth authorization URL.

        PKCE is required by the Slack MCP OAuth metadata.
        """

        if not state:
            raise ValueError(
                "state cannot be empty."
            )

        self._require_config()

        if not code_challenge:
            raise ValueError(
                "Slack MCP OAuth requires a PKCE "
                "code challenge."
            )

        params = {
            "client_id": settings.slack_client_id,
            "redirect_uri": settings.slack_redirect_uri,
            "scope": settings.slack_oauth_scope,
            "state": state,
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        return (
            f"{self.AUTHORIZE_URL}?"
            f"{urlencode(params)}"
        )

    # ========================================================
    # CODE EXCHANGE
    # ========================================================

    async def exchange_code(
        self,
        code: str,
        code_verifier: str | None = None,
    ) -> OAuthToken:
        """
        Exchange Slack MCP OAuth authorization code.

        Slack requires PKCE for the MCP OAuth flow.
        """

        self._require_config()

        if not code:
            raise ValueError(
                "Slack authorization code cannot be empty."
            )

        if not code_verifier:
            raise ValueError(
                "Slack MCP OAuth requires a PKCE "
                "code verifier."
            )

        payload = {
            "client_id": settings.slack_client_id,
            "client_secret": settings.slack_client_secret,
            "code": code,
            "redirect_uri": settings.slack_redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }

        async with httpx.AsyncClient(
            timeout=15.0,
        ) as client:

            response = await client.post(
                self.TOKEN_URL,
                data=payload,
            )

            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                raise RuntimeError(
                    data.get(
                        "error",
                        "Slack OAuth token exchange failed.",
                    )
                )

            access_token = data.get(
                "access_token"
            )

            if not access_token:
                raise RuntimeError(
                    "Slack did not return an access token."
                )

            expires_at = None

            expires_in = data.get(
                "expires_in"
            )

            if expires_in is not None:
                expires_at = (
                    datetime.utcnow()
                    + timedelta(
                        seconds=int(expires_in)
                    )
                )

            return OAuthToken(
                access_token=access_token,
                refresh_token=data.get(
                    "refresh_token"
                ),
                expires_at=expires_at,
                scope=data.get("scope"),
                provider_user_id=(
                    data.get("authed_user", {})
                    .get("id")
                ),
            )

    # ========================================================
    # USER
    # ========================================================

    async def get_user(
        self,
        access_token: str,
    ) -> dict:
        """
        Validate the Slack access token and retrieve
        the authenticated Slack user information.
        """

        if not access_token:
            raise ValueError(
                "Slack access token cannot be empty."
            )

        headers = {
            "Authorization": (
                f"Bearer {access_token}"
            ),
        }

        async with httpx.AsyncClient(
            timeout=15.0,
        ) as client:

            response = await client.get(
                self.USER_URL,
                headers=headers,
            )

            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                raise RuntimeError(
                    data.get(
                        "error",
                        "Slack authentication failed.",
                    )
                )

            return data

    # ========================================================
    # REFRESH TOKEN
    # ========================================================

    async def refresh_token(
        self,
        refresh_token: str,
    ) -> OAuthToken:
        """
        Refresh a Slack MCP OAuth token.
        """

        self._require_config()

        if not refresh_token:
            raise ValueError(
                "Slack refresh token cannot be empty."
            )

        payload = {
            "client_id": settings.slack_client_id,
            "client_secret": settings.slack_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        async with httpx.AsyncClient(
            timeout=15.0,
        ) as client:

            response = await client.post(
                self.TOKEN_URL,
                data=payload,
            )

            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                raise RuntimeError(
                    data.get(
                        "error",
                        "Slack token refresh failed.",
                    )
                )

            access_token = data.get(
                "access_token"
            )

            if not access_token:
                raise RuntimeError(
                    "Slack did not return a refreshed "
                    "access token."
                )

            expires_at = None

            expires_in = data.get(
                "expires_in"
            )

            if expires_in is not None:
                expires_at = (
                    datetime.utcnow()
                    + timedelta(
                        seconds=int(expires_in)
                    )
                )

            return OAuthToken(
                access_token=access_token,
                refresh_token=(
                    data.get("refresh_token")
                    or refresh_token
                ),
                expires_at=expires_at,
                scope=data.get("scope"),
                provider_user_id=(
                    data.get("authed_user", {})
                    .get("id")
                ),
            )

