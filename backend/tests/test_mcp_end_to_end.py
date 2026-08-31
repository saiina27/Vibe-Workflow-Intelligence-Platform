from unittest.mock import MagicMock

import pytest

from app.ai.tool_calling import ToolCallingService
from app.ai.tools.context import ToolContext
from app.ai.tools.registry import ToolRegistry
from app.ai.providers.base import AIProvider
from app.mcp.permissions import MCPPermissionService
from app.mcp.tool_adapter import MCPToolAdapter
from app.schemas.ai import AIResponse, ToolCall


# ============================================================
# HELPERS
# ============================================================


def make_context():
    context = MagicMock(spec=ToolContext)

    context.user_id = 42
    context.workspace_id = 7
    context.db = MagicMock()

    context.is_tool_allowed.return_value = True

    return context


def make_mcp_tool():
    tool = MagicMock()

    tool.name = "github_get_pull_request"
    tool.description = "Get a GitHub pull request"
    tool.input_schema = {
        "type": "object",
        "properties": {
            "pull_number": {
                "type": "integer",
            }
        },
        "required": ["pull_number"],
    }

    return tool


def make_mcp_client():
    client = MagicMock()

    client.call_tool.return_value = {
        "number": 123,
        "title": "Fix authentication bug",
        "state": "open",
    }

    return client


def make_registry(client):
    registry = ToolRegistry()

    adapter = MCPToolAdapter(
        client=client,
        tool=make_mcp_tool(),
        plugin_name="github",
    )

    registry.register(adapter)

    return registry


def make_provider():
    provider = MagicMock(spec=AIProvider)

    provider.generate_with_tool_results.return_value = AIResponse(
        content="PR #123 is open and fixes the authentication bug.",
        model="test-model",
        provider="gemini",
    )

    return provider


def make_initial_response():
    return AIResponse(
        content=None,
        model="test-model",
        provider="gemini",
        tool_calls=[
            ToolCall(
                id="call_123",
                name="github_get_pull_request",
                arguments={
                    "pull_number": 123,
                },
            )
        ],
    )


def make_permission_service():
    permission_service = MagicMock(
        spec=MCPPermissionService
    )

    permission_service.is_tool_allowed.return_value = True

    return permission_service


# ============================================================
# MCP END-TO-END TOOL EXECUTION
# ============================================================


def test_mcp_tool_executes_through_complete_tool_calling_lifecycle():

    client = make_mcp_client()

    registry = make_registry(client)

    context = make_context()

    provider = make_provider()

    permission_service = make_permission_service()

    service = ToolCallingService(
        registry=registry,
        provider=provider,
        context=context,
        mcp_permission_service=permission_service,
    )

    initial_response = make_initial_response()

    request = MagicMock()

    final_response = service.complete_with_tool_results(
        request=request,
        initial_response=initial_response,
    )

    # --------------------------------------------------------
    # FINAL AI RESPONSE
    # --------------------------------------------------------

    assert final_response.content == (
        "PR #123 is open and fixes the authentication bug."
    )

    # --------------------------------------------------------
    # MCP TOOL WAS ACTUALLY CALLED
    # --------------------------------------------------------

    client.call_tool.assert_called_once_with(
        tool_name="github_get_pull_request",
        arguments={
            "pull_number": 123,
        },
    )

    # --------------------------------------------------------
    # MCP PERMISSION WAS CHECKED
    # --------------------------------------------------------

    permission_service.is_tool_allowed.assert_called_once()

    # --------------------------------------------------------
    # SAME PROVIDER RECEIVED TOOL RESULT
    # --------------------------------------------------------

    provider.generate_with_tool_results.assert_called_once()

    call_kwargs = (
        provider.generate_with_tool_results.call_args.kwargs
    )

    assert call_kwargs["request"] is request
    assert call_kwargs["original_response"] is initial_response

    tool_results = call_kwargs["tool_results"]

    assert len(tool_results) == 1

    assert tool_results[0]["tool_call_id"] == "call_123"
    assert tool_results[0]["name"] == (
        "github_get_pull_request"
    )

    assert tool_results[0]["result"]["success"] is True


# ============================================================
# MCP PERMISSION DENIAL
# ============================================================


def test_mcp_permission_denial_prevents_mcp_execution():

    client = make_mcp_client()

    registry = make_registry(client)

    context = make_context()

    provider = make_provider()

    permission_service = make_permission_service()

    permission_service.is_tool_allowed.return_value = False

    service = ToolCallingService(
        registry=registry,
        provider=provider,
        context=context,
        mcp_permission_service=permission_service,
    )

    response = make_initial_response()

    results = service.execute_tool_calls(response)

    assert len(results) == 1

    assert results[0].result["success"] is False

    assert "not allowed" in results[0].result["error"]

    client.call_tool.assert_not_called()


# ============================================================
# MCP FAILURE IS RETURNED AS TOOL RESULT
# ============================================================


def test_mcp_failure_is_returned_to_provider():

    client = make_mcp_client()

    client.call_tool.side_effect = RuntimeError(
        "GitHub MCP server unavailable"
    )

    registry = make_registry(client)

    context = make_context()

    provider = make_provider()

    permission_service = make_permission_service()

    service = ToolCallingService(
        registry=registry,
        provider=provider,
        context=context,
        mcp_permission_service=permission_service,
    )

    response = make_initial_response()

    results = service.execute_tool_calls(response)

    assert len(results) == 1

    assert results[0].result == {
        "success": False,
        "error": (
            "Tool 'github_get_pull_request' execution failed: "
            "GitHub MCP server unavailable"
        ),
    }

    client.call_tool.assert_called_once()


# ============================================================
# MULTI-ITERATION MCP LOOP
# ============================================================


def test_mcp_tool_calling_can_continue_to_second_provider_round():

    client = make_mcp_client()

    registry = make_registry(client)

    context = make_context()

    provider = make_provider()

    permission_service = make_permission_service()

    second_tool_call_response = AIResponse(
        content=None,
        model="test-model",
        provider="gemini",
        tool_calls=[
            ToolCall(
                id="call_456",
                name="github_get_pull_request",
                arguments={
                    "pull_number": 456,
                },
            )
        ],
    )

    final_response = AIResponse(
        content="I checked both pull requests.",
        model="test-model",
        provider="gemini",
    )

    provider.generate_with_tool_results.side_effect = [
        second_tool_call_response,
        final_response,
    ]

    client.call_tool.side_effect = [
        {"number": 123, "state": "open"},
        {"number": 456, "state": "merged"},
    ]

    service = ToolCallingService(
        registry=registry,
        provider=provider,
        context=context,
        mcp_permission_service=permission_service,
    )

    initial_response = make_initial_response()

    final = service.complete_with_tool_results(
        request=MagicMock(),
        initial_response=initial_response,
    )

    assert final.content == (
        "I checked both pull requests."
    )

    assert client.call_tool.call_count == 2

    assert provider.generate_with_tool_results.call_count == 2


# ============================================================
# TOOL RESULT BOUNDING
# ============================================================


def test_mcp_large_result_is_bounded_before_provider_round_trip():

    huge_result = {
        "number": 123,
        "body": "x" * 10_000,
    }

    bounded = ToolCallingService._bound_tool_result(
        {
            "success": True,
            "data": huge_result,
        }
    )

    assert bounded["success"] is True

    assert len(str(bounded["data"])) <= (
        ToolCallingService.MAX_TOOL_RESULT_CHARS
    )
