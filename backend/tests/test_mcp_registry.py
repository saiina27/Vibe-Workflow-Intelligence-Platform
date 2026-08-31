import pytest

from app.mcp.registry import (
    MCPPlugin,
    MCPPluginRegistry,
)
from app.mcp.server_manager import MCPServerConfig


def make_plugin(
    name="github",
    enabled=True,
):
    return MCPPlugin(
        name=name,
        display_name=name.title(),
        server_config=MCPServerConfig(
            name=name,
            command="python",
            args=("-m", "example_server"),
        ),
        enabled=enabled,
    )


def test_register_plugin():
    registry = MCPPluginRegistry()

    plugin = make_plugin()

    registry.register(plugin)

    assert registry.get("github") == plugin


def test_duplicate_plugin_is_rejected():
    registry = MCPPluginRegistry()

    registry.register(make_plugin())

    with pytest.raises(ValueError):
        registry.register(make_plugin())


def test_list_plugins():
    registry = MCPPluginRegistry()

    registry.register(make_plugin("github"))
    registry.register(make_plugin("slack"))

    assert registry.list_plugins() == [
        registry.get("github"),
        registry.get("slack"),
    ]


def test_list_enabled_plugins():
    registry = MCPPluginRegistry()

    registry.register(
        make_plugin(
            "github",
            enabled=True,
        )
    )

    registry.register(
        make_plugin(
            "slack",
            enabled=False,
        )
    )

    enabled = registry.list_enabled_plugins()

    assert [plugin.name for plugin in enabled] == [
        "github"
    ]


def test_disable_plugin():
    registry = MCPPluginRegistry()

    registry.register(make_plugin())

    plugin = registry.disable("github")

    assert plugin.enabled is False
    assert registry.get("github").enabled is False


def test_enable_plugin():
    registry = MCPPluginRegistry()

    registry.register(
        make_plugin(
            enabled=False,
        )
    )

    plugin = registry.enable("github")

    assert plugin.enabled is True
    assert registry.get("github").enabled is True


def test_unregister_plugin():
    registry = MCPPluginRegistry()

    registry.register(make_plugin())

    registry.unregister("github")

    assert registry.contains("github") is False


def test_unknown_plugin_raises():
    registry = MCPPluginRegistry()

    with pytest.raises(ValueError):
        registry.get("github")


def test_empty_plugin_name_is_rejected():
    registry = MCPPluginRegistry()

    plugin = make_plugin(name="   ")

    with pytest.raises(ValueError):
        registry.register(plugin)
