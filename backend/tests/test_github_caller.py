import asyncio

import pytest

from app.api.routes import dev_events as routes


class FakeManager:
    def __init__(self):
        self.connected = 0
        self.disconnected = 0

    async def connect_github(self, db, user_id, registry):
        self.connected += 1
        return 0

    async def disconnect_github(self, user_id):
        self.disconnected += 1


class FakePermissions:
    def add_workspace_plugin(self, workspace_id, name):
        pass


@pytest.fixture
def manager(monkeypatch):
    fake = FakeManager()
    monkeypatch.setattr(routes, "mcp_integration_manager", fake)
    monkeypatch.setattr(routes, "mcp_permission_service", FakePermissions())
    monkeypatch.setattr(routes, "get_user_integration", lambda **kwargs: object())
    return fake


async def use(fail=False):
    async with routes.github_caller(db=None, workspace_id=1, user_id=1) as call:
        with pytest.raises(PermissionError):
            call("create_pull_request", {})

        if fail:
            raise RuntimeError("boom")


def test_shared_github_connection_is_never_closed(manager):
    asyncio.run(use())

    assert manager.connected == 1
    assert manager.disconnected == 0


def test_connection_stays_open_even_when_the_work_fails(manager):
    with pytest.raises(RuntimeError):
        asyncio.run(use(fail=True))

    assert manager.disconnected == 0
