from app.ai.tools.base import BaseTool
from app.schemas.ai import ToolDefinition


class ToolRegistry:
    """
    Registry for Vibe AI tools.
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool using its unique name.
        """

        if tool.name in self._tools:
            raise ValueError(
                f"Tool '{tool.name}' is already registered."
            )

        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        """
        Retrieve a registered tool by name.
        """

        tool = self._tools.get(name)

        if tool is None:
            raise ValueError(
                f"Tool '{name}' is not registered."
            )

        return tool

    def list_tools(self) -> list[BaseTool]:
        """
        Return all registered tools.
        """

        return list(self._tools.values())

    def definitions(self) -> list[ToolDefinition]:
        """
        Return provider-independent tool definitions.
        """

        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
            )
            for tool in self._tools.values()
        ]