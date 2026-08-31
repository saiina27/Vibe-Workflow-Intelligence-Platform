from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OAuthToken:
    """
    Provider-independent OAuth token response.
    """

    access_token: str

    refresh_token: str | None = None

    expires_at: datetime | None = None

    scope: str | None = None

    provider_user_id: str | None = None


class OAuthProvider(ABC):
    """
    Provider-independent OAuth contract.

    GitHub, Slack, and future providers implement
    this interface independently.

    The rest of Vibe does not need to know provider-specific
    OAuth implementation details.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the provider identifier.

        Example:
            github
            slack
        """
        pass

    @abstractmethod
    def get_authorization_url(
        self,
        state: str,
    ) -> str:
        """
        Build the provider OAuth authorization URL.
        """
        pass

    @abstractmethod
    async def exchange_code(
        self,
        code: str,
    ) -> OAuthToken:
        """
        Exchange an OAuth authorization code for tokens.
        """
        pass

    @abstractmethod
    async def refresh_token(
        self,
        refresh_token: str,
    ) -> OAuthToken:
        """
        Refresh an expired OAuth access token.
        """
        pass