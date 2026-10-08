from app.ai.tools.context import ToolContext
from app.ai.tools.permissions import ToolPermissionService


def make_context(
    workspace_id=1,
    user_id=1,
    allowed_tools=None,
):
    return ToolContext(
        db=None,
        workspace_id=workspace_id,
        user_id=user_id,
        allowed_tools=allowed_tools,
    )


def test_default_tools_are_allowed():
    service = ToolPermissionService()

    context = make_context()

    allowed = service.get_allowed_tools(context)

    assert allowed == {
        "search_memory",
        "search_knowledge",
        "search_web",
        "search_chats",
        "github",
        "slack",
    }


def test_workspace_permission_overrides_default():
    service = ToolPermissionService()

    service.set_workspace_tools(
        workspace_id=1,
        tools={"search_memory"},
    )

    context = make_context(
        workspace_id=1,
    )

    assert service.get_allowed_tools(context) == {
        "search_memory",
    }


def test_user_permission_used_when_workspace_has_no_override():
    service = ToolPermissionService()

    service.set_user_tools(
        user_id=10,
        tools={"search_knowledge"},
    )

    context = make_context(
        workspace_id=99,
        user_id=10,
    )

    assert service.get_allowed_tools(context) == {
        "search_knowledge",
    }


def test_request_restriction_can_only_reduce_permissions():
    service = ToolPermissionService()

    service.set_workspace_tools(
        workspace_id=1,
        tools={
            "search_memory",
            "search_knowledge",
        },
    )

    context = make_context(
        workspace_id=1,
        allowed_tools=frozenset({
            "search_memory",
        }),
    )

    assert service.get_allowed_tools(context) == {
        "search_memory",
    }


def test_request_restriction_cannot_grant_permission():
    service = ToolPermissionService()

    service.set_workspace_tools(
        workspace_id=1,
        tools={"search_memory"},
    )

    context = make_context(
        workspace_id=1,
        allowed_tools=frozenset({
            "search_web",
        }),
    )

    assert service.get_allowed_tools(context) == set()


def test_unauthorized_tool_is_denied():
    service = ToolPermissionService()

    context = make_context()

    assert service.is_allowed(
        "delete_workspace",
        context,
    ) is False
