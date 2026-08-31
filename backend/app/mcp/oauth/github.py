from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.mcp.oauth.base import OAuthProvider, OAuthToken


class GitHubOAuthProvider(OAuthProvider):
    """
    GitHub OAuth implementation.

    Provider-specific OAuth behavior stays inside this class.
    """

    AUTHORIZE_URL = (
        "https://github.com/login/oauth/authorize"
    )

    TOKEN_URL = (
        "https://github.com/login/oauth/access_token"
    )

    USER_URL = "https://api.github.com/user"

    @property
    def name(self) -> str:
        return "github"

    def _require_config(self) -> None:
        if not settings.github_client_id:
            raise RuntimeError(
                "GitHub OAuth client ID is not configured."
            )

        if not settings.github_client_secret:
            raise RuntimeError(
                "GitHub OAuth client secret is not configured."
            )

        if not settings.github_redirect_uri:
            raise RuntimeError(
                "GitHub OAuth redirect URI is not configured."
            )

    def get_authorization_url(
        self,
        state: str,
    ) -> str:
        if not state:
            raise ValueError(
                "state cannot be empty"
            )

        self._require_config()

        params = {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_redirect_uri,
            "scope": settings.github_oauth_scope,
            "state": state,
        }

        return (
            f"{self.AUTHORIZE_URL}?"
            f"{urlencode(params)}"
        )

    async def exchange_code(
        self,
        code: str,
    ) -> OAuthToken:
        self._require_config()

        if not code:
            raise ValueError(
                "GitHub authorization code cannot be empty."
            )

        payload = {
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "code": code,
            "redirect_uri": settings.github_redirect_uri,
        }

        headers = {
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(
            timeout=15.0,
        ) as client:

            response = await client.post(
                self.TOKEN_URL,
                data=payload,
                headers=headers,
            )

            response.raise_for_status()

            data = response.json()

            access_token = data.get(
                "access_token"
            )

            if not access_token:
                raise RuntimeError(
                    "GitHub did not return an access token."
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
            )

    async def get_user(
        self,
        access_token: str,
    ) -> dict:
        if not access_token:
            raise ValueError(
                "GitHub access token cannot be empty."
            )

        headers = {
            "Accept": "application/vnd.github+json",
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

            return response.json()

    async def refresh_token(
        self,
        refresh_token: str,
    ) -> OAuthToken:
        self._require_config()

        if not refresh_token:
            raise ValueError(
                "GitHub refresh token cannot be empty."
            )

        payload = {
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        headers = {
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(
            timeout=15.0,
        ) as client:

            response = await client.post(
                self.TOKEN_URL,
                data=payload,
                headers=headers,
            )

            response.raise_for_status()

            data = response.json()

            access_token = data.get(
                "access_token"
            )

            if not access_token:
                raise RuntimeError(
                    "GitHub did not return a refreshed access token."
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
            )