from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.chat_service import get_workspace_chats


def make_db(workspace_owner_id=1, chats=None):
    db = MagicMock()

    workspace = MagicMock()
    workspace.user_id = workspace_owner_id

    db.query.return_value.filter.return_value.first.return_value = workspace

    (
        db.query.return_value
        .filter.return_value
        .order_by.return_value
        .all.return_value
    ) = chats or []

    return db


def make_unauthorized_db():
    db = MagicMock()

    (
        db.query.return_value
        .filter.return_value
        .first.return_value
    ) = None

    return db


def test_workspace_owner_can_access_chats():
    chat_1 = MagicMock()
    chat_1.id = 1

    chat_2 = MagicMock()
    chat_2.id = 2

    db = make_db(
        workspace_owner_id=1,
        chats=[chat_1, chat_2],
    )

    result = get_workspace_chats(
        db=db,
        workspace_id=1,
        user_id=1,
    )

    assert result == [chat_1, chat_2]


def test_other_user_cannot_access_workspace_chats():
    db = make_unauthorized_db()

    with pytest.raises(HTTPException) as exc_info:
        get_workspace_chats(
            db=db,
            workspace_id=1,
            user_id=2,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Workspace not found"


def test_archive_requires_workspace_access():
    from app.services.chat_service import archive_chat

    db = make_unauthorized_db()

    with pytest.raises(HTTPException) as exc_info:
        archive_chat(
            db=db,
            workspace_id=1,
            chat_id=1,
            user_id=2,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Workspace not found"


def test_restore_requires_workspace_access():
    from app.services.chat_service import restore_chat

    db = make_unauthorized_db()

    with pytest.raises(HTTPException) as exc_info:
        restore_chat(
            db=db,
            workspace_id=1,
            chat_id=1,
            user_id=2,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Workspace not found"


def test_topic_search_requires_workspace_access():
    from app.services.chat_service import get_chats_by_topic

    db = make_unauthorized_db()

    with pytest.raises(HTTPException) as exc_info:
        get_chats_by_topic(
            db=db,
            workspace_id=1,
            topic="python",
            user_id=2,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Workspace not found"


def test_status_search_requires_workspace_access():
    from app.services.chat_service import get_chats_by_status

    db = make_unauthorized_db()

    with pytest.raises(HTTPException) as exc_info:
        get_chats_by_status(
            db=db,
            workspace_id=1,
            status="active",
            user_id=2,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Workspace not found"
