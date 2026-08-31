
from datetime import datetime, timedelta

import pytest

from app.mcp.oauth.base import OAuthToken
from app.mcp.oauth.encryption import decrypt_token
from app.models.external_integration import ExternalIntegration
from app.services.external_integration_service import (
    delete_user_integration,
    get_user_integration,
    save_oauth_token,
)


class FakeQuery:
    def __init__(self, integration):
        self.integration = integration

    def filter(self, *args):
        return self

    def first(self):
        return self.integration


class FakeDB:
    def __init__(self):
        self.integration = None
        self.added = []
        self.deleted = []

    def query(self, model):
        return FakeQuery(self.integration)

    def add(self, obj):
        self.added.append(obj)

        if isinstance(obj, ExternalIntegration):
            self.integration = obj

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def delete(self, obj):
        self.deleted.append(obj)

        if obj is self.integration:
            self.integration = None


def make_token(
    access_token="access-token",
    refresh_token="refresh-token",
    provider_user_id="12345",
):
    return OAuthToken(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        scope="repo",
        provider_user_id=provider_user_id,
    )


# ============================================================
# EXISTING OAUTH INTEGRATION TESTS
# ============================================================


def test_save_oauth_token_creates_integration():
    db = FakeDB()

    integration = save_oauth_token(
        db=db,
        user_id=1,
        provider="github",
        token=make_token(),
    )

    assert integration.user_id == 1
    assert integration.provider == "github"
    assert integration.access_token != "access-token"

    assert (
        decrypt_token(integration.access_token)
        == "access-token"
    )

    assert integration.refresh_token != "refresh-token"

    assert (
        decrypt_token(integration.refresh_token)
        == "refresh-token"
    )

    assert integration.provider_user_id == "12345"
    assert integration.scope == "repo"

    assert len(db.added) == 1


def test_save_oauth_token_updates_existing_integration():
    db = FakeDB()

    existing = ExternalIntegration(
        user_id=1,
        provider="github",
        access_token="old-token",
        refresh_token="old-refresh",
    )

    db.integration = existing

    token = make_token(
        access_token="new-token",
        refresh_token="new-refresh",
    )

    integration = save_oauth_token(
        db=db,
        user_id=1,
        provider="github",
        token=token,
    )

    assert integration is existing
    assert integration.access_token != "new-token"

    assert (
        decrypt_token(integration.access_token)
        == "new-token"
    )

    assert integration.refresh_token != "new-refresh"

    assert (
        decrypt_token(integration.refresh_token)
        == "new-refresh"
    )

    assert len(db.added) == 1


def test_get_user_integration():
    db = FakeDB()

    existing = ExternalIntegration(
        user_id=10,
        provider="github",
        access_token="token",
    )

    db.integration = existing

    result = get_user_integration(
        db=db,
        user_id=10,
        provider="github",
    )

    assert result is existing


def test_delete_user_integration():
    db = FakeDB()

    existing = ExternalIntegration(
        user_id=1,
        provider="github",
        access_token="token",
    )

    db.integration = existing

    deleted = delete_user_integration(
        db=db,
        user_id=1,
        provider="github",
    )

    assert deleted is True
    assert db.deleted == [existing]
    assert db.integration is None


def test_delete_missing_integration_returns_false():
    db = FakeDB()

    deleted = delete_user_integration(
        db=db,
        user_id=1,
        provider="github",
    )

    assert deleted is False


# ============================================================
# PROVIDER VALIDATION
# ============================================================


@pytest.mark.parametrize(
    "provider",
    [
        "notion",
        "jira",
        "google",
        "",
    ],
)
def test_unsupported_provider_is_rejected(provider):
    db = FakeDB()

    with pytest.raises(
        ValueError,
        match="Unsupported integration provider",
    ):
        save_oauth_token(
            db=db,
            user_id=1,
            provider=provider,
            token=make_token(),
        )


def test_empty_access_token_is_rejected():
    db = FakeDB()

    with pytest.raises(
        ValueError,
        match="OAuth access token cannot be empty",
    ):
        save_oauth_token(
            db=db,
            user_id=1,
            provider="github",
            token=make_token(
                access_token="",
            ),
        )


def test_provider_name_is_normalized():
    db = FakeDB()

    integration = save_oauth_token(
        db=db,
        user_id=1,
        provider=" GitHub ",
        token=make_token(),
    )

    assert integration.provider == "github"


# ============================================================
# SLACK OAUTH TESTS
# ============================================================


def test_save_slack_oauth_token_creates_integration():
    db = FakeDB()

    token = make_token(
        access_token="slack-access-token",
        refresh_token="slack-refresh-token",
        provider_user_id="U12345",
    )

    integration = save_oauth_token(
        db=db,
        user_id=1,
        provider="slack",
        token=token,
    )

    assert integration.user_id == 1
    assert integration.provider == "slack"

    assert integration.access_token != "slack-access-token"
    assert (
        decrypt_token(integration.access_token)
        == "slack-access-token"
    )

    assert integration.refresh_token != "slack-refresh-token"
    assert (
        decrypt_token(integration.refresh_token)
        == "slack-refresh-token"
    )

    assert integration.provider_user_id == "U12345"
    assert integration.scope == "repo"

    assert len(db.added) == 1


def test_save_slack_oauth_token_updates_existing_integration():
    db = FakeDB()

    existing = ExternalIntegration(
        user_id=1,
        provider="slack",
        access_token="old-slack-token",
        refresh_token="old-slack-refresh",
    )

    db.integration = existing

    token = make_token(
        access_token="new-slack-token",
        refresh_token="new-slack-refresh",
        provider_user_id="U67890",
    )

    integration = save_oauth_token(
        db=db,
        user_id=1,
        provider="slack",
        token=token,
    )

    assert integration is existing

    assert integration.access_token != "new-slack-token"
    assert (
        decrypt_token(integration.access_token)
        == "new-slack-token"
    )

    assert integration.refresh_token != "new-slack-refresh"
    assert (
        decrypt_token(integration.refresh_token)
        == "new-slack-refresh"
    )

    assert integration.provider_user_id == "U67890"

    assert len(db.added) == 1


def test_get_slack_user_integration():
    db = FakeDB()

    existing = ExternalIntegration(
        user_id=10,
        provider="slack",
        access_token="slack-token",
    )

    db.integration = existing

    result = get_user_integration(
        db=db,
        user_id=10,
        provider="slack",
    )

    assert result is existing
    assert result.provider == "slack"

