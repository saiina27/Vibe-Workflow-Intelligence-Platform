from __future__ import annotations

import asyncio

from app.ai.tools.registry import ToolRegistry
from app.core.config import settings
from app.db.session import SessionLocal
from app.mcp.runtime import (
    mcp_integration_manager,
    mcp_plugin_registry,
    mcp_server_manager,
)
from app.repositories import external_integration_repository


GITHUB_USER_ID = 3
SLACK_USER_ID = 1


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)

    print(f"PASS  {message}")


async def main() -> None:
    print()
    print("=" * 64)
    print("        SPRINT 12 — MCP FINAL ACCEPTANCE TEST")
    print("=" * 64)

    db = SessionLocal()

    github_runtime = None
    slack_runtime = None

    try:
        # ----------------------------------------------------
        # 1. CONFIGURATION
        # ----------------------------------------------------

        print("\n[1] Configuration")

        check(
            bool(settings.github_client_id),
            "GitHub OAuth client configured",
        )

        check(
            bool(settings.github_client_secret),
            "GitHub OAuth secret configured",
        )

        check(
            bool(settings.github_redirect_uri),
            "GitHub OAuth redirect URI configured",
        )

        check(
            bool(settings.slack_client_id),
            "Slack OAuth client configured",
        )

        check(
            bool(settings.slack_client_secret),
            "Slack OAuth secret configured",
        )

        check(
            bool(settings.slack_redirect_uri),
            "Slack OAuth redirect URI configured",
        )

        check(
            bool(settings.slack_mcp_url),
            "Slack MCP URL configured",
        )

        # ----------------------------------------------------
        # 2. PLUGIN REGISTRY
        # ----------------------------------------------------

        print("\n[2] Plugin Registry")

        github_plugin = mcp_plugin_registry.get("github")
        slack_plugin = mcp_plugin_registry.get("slack")

        check(
            github_plugin.enabled,
            "GitHub MCP plugin enabled",
        )

        check(
            slack_plugin.enabled,
            "Slack MCP plugin enabled",
        )

        check(
            github_plugin.auth_type == "oauth",
            "GitHub uses OAuth",
        )

        check(
            slack_plugin.auth_type == "oauth",
            "Slack uses OAuth",
        )

        # ----------------------------------------------------
        # 3. OAUTH PERSISTENCE
        # ----------------------------------------------------

        print("\n[3] OAuth Persistence")

        github_integration = (
            external_integration_repository.get_integration(
                db=db,
                user_id=GITHUB_USER_ID,
                provider="github",
            )
        )

        slack_integration = (
            external_integration_repository.get_integration(
                db=db,
                user_id=SLACK_USER_ID,
                provider="slack",
            )
        )

        check(
            github_integration is not None,
            "GitHub OAuth integration exists in database",
        )

        check(
            slack_integration is not None,
            "Slack OAuth integration exists in database",
        )

        check(
            bool(github_integration.access_token),
            "GitHub encrypted access token exists",
        )

        check(
            bool(slack_integration.access_token),
            "Slack encrypted access token exists",
        )

        # ----------------------------------------------------
        # 4. GITHUB REAL MCP
        # ----------------------------------------------------

        print("\n[4] GitHub MCP")

        github_registry = ToolRegistry()

        github_registered = (
            await mcp_integration_manager.connect_github(
                db=db,
                user_id=GITHUB_USER_ID,
                registry=github_registry,
            )
        )

        github_runtime = (
            mcp_integration_manager
            ._get_github_runtime_name(GITHUB_USER_ID)
        )

        check(
            github_runtime
            in mcp_server_manager.list_connected_servers(),
            "GitHub MCP server connected",
        )

        check(
            github_registered > 0,
            f"GitHub MCP discovered {github_registered} tools",
        )

        github_tools = github_registry.list_tools()

        check(
            len(github_tools) >= 20,
            f"GitHub exposes {len(github_tools)} tools",
        )

        github_tool_names = {
            tool.name
            for tool in github_tools
        }

        for required_tool in (
            "get_me",
            "list_pull_requests",
            "pull_request_read",
            "list_issues",
            "issue_read",
            "list_commits",
            "get_commit",
        ):
            check(
                required_tool in github_tool_names,
                f"GitHub tool available: {required_tool}",
            )

        # ----------------------------------------------------
        # 5. GITHUB REAL TOOL EXECUTION
        # ----------------------------------------------------

        print("\n[5] GitHub Real Tool Execution")

        get_me = next(
            tool
            for tool in github_tools
            if tool.name == "get_me"
        )

        result = get_me.execute()

        check(
            result is not None,
            "GitHub get_me returned a response",
        )

        result_text = str(result)

        check(
            "saiina27" in result_text,
            "GitHub response contains authenticated account",
        )

        # ----------------------------------------------------
        # 6. SLACK REAL MCP
        # ----------------------------------------------------

        print("\n[6] Slack MCP")

        slack_registry = ToolRegistry()

        slack_registered = (
            await mcp_integration_manager.connect_slack(
                db=db,
                user_id=SLACK_USER_ID,
                registry=slack_registry,
            )
        )

        slack_runtime = (
            mcp_integration_manager
            ._get_slack_runtime_name(SLACK_USER_ID)
        )

        check(
            slack_runtime
            in mcp_server_manager.list_connected_servers(),
            "Slack MCP server connected",
        )

        check(
            slack_registered > 0,
            f"Slack MCP discovered {slack_registered} tools",
        )

        slack_tools = slack_registry.list_tools()

        check(
            len(slack_tools) >= 1,
            f"Slack exposes {len(slack_tools)} tools",
        )

        slack_tool_names = {
            tool.name
            for tool in slack_tools
        }

        check(
            "slack_search_public" in slack_tool_names,
            "Slack search tool registered",
        )

        # ----------------------------------------------------
        # 7. SLACK REAL SEARCH
        # ----------------------------------------------------

        print("\n[7] Slack Real Search")

        slack_search = next(
            tool
            for tool in slack_tools
            if tool.name == "slack_search_public"
        )

        try:
            slack_result = slack_search.execute(
                keywords=["vibe"],
                natural_language_query="Search Slack for vibe",
                response_format="concise",
            )

            check(
                slack_result is not None,
                "Slack search returned a response",
            )

        except Exception as exc:
            raise AssertionError(
                f"Slack real search failed: {exc}"
            ) from exc

        # ----------------------------------------------------
        # 8. PERMISSION / IDENTITY
        # ----------------------------------------------------

        print("\n[8] MCP Permission / Identity")

        check(
            github_plugin.metadata["provider"] == "github",
            "GitHub plugin identity preserved",
        )

        check(
            slack_plugin.metadata["provider"] == "slack",
            "Slack plugin identity preserved",
        )

        check(
            all(
                getattr(tool, "plugin_name", None) == "github"
                for tool in github_tools
            ),
            "GitHub discovered tools preserve plugin identity",
        )

        check(
            all(
                getattr(tool, "plugin_name", None) == "slack"
                for tool in slack_tools
            ),
            "Slack discovered tools preserve plugin identity",
        )

        # ----------------------------------------------------
        # 9. CLEAN DISCONNECT
        # ----------------------------------------------------

        print("\n[9] Clean Disconnect")

        await mcp_integration_manager.disconnect_github(
            user_id=GITHUB_USER_ID,
        )

        check(
            github_runtime
            not in mcp_server_manager.list_connected_servers(),
            "GitHub disconnected cleanly",
        )

        await mcp_integration_manager.disconnect_slack(
            user_id=SLACK_USER_ID,
        )

        check(
            slack_runtime
            not in mcp_server_manager.list_connected_servers(),
            "Slack disconnected cleanly",
        )

        # ----------------------------------------------------
        # 10. NO CONNECTION LEAK
        # ----------------------------------------------------

        print("\n[10] Runtime Leak Check")

        connected = (
            mcp_server_manager.list_connected_servers()
        )

        check(
            github_runtime not in connected,
            "No GitHub MCP connection leaked",
        )

        check(
            slack_runtime not in connected,
            "No Slack MCP connection leaked",
        )

        print()
        print("=" * 64)
        print("              SPRINT 12: PASS")
        print("=" * 64)
        print()
        print("MCP Core                 PASS")
        print("GitHub MCP               PASS")
        print("Slack MCP                PASS")
        print("OAuth persistence        PASS")
        print("Tool discovery           PASS")
        print("Real tool execution      PASS")
        print("Plugin identity          PASS")
        print("Clean disconnect         PASS")
        print("Connection leak check    PASS")
        print()
        print("Sprint 12 acceptance gate PASSED.")
        print()

    finally:
        # ----------------------------------------------------
        # DEFENSIVE CLEANUP
        # ----------------------------------------------------

        try:
            connected = (
                mcp_server_manager.list_connected_servers()
            )

            if github_runtime in connected:
                await mcp_integration_manager.disconnect_github(
                    user_id=GITHUB_USER_ID,
                )

            connected = (
                mcp_server_manager.list_connected_servers()
            )

            if slack_runtime in connected:
                await mcp_integration_manager.disconnect_slack(
                    user_id=SLACK_USER_ID,
                )

        except Exception as exc:
            print(
                f"WARNING: defensive MCP cleanup failed: {exc}"
            )

        db.close()


if __name__ == "__main__":
    asyncio.run(main())
