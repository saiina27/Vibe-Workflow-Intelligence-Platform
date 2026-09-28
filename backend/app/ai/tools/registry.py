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

    @staticmethod
    def _tools_for_only_use(prompt: str, tools: list) -> list:
        """
        If the prompt says "only use github/slack/web/memory/
        knowledge", return just the tools of those groups.
        Returns [] when nothing matches, so callers fall back
        to the normal selection.
        """

        text = prompt.lower()

        def is_github(t) -> bool:
            return getattr(t, "plugin_name", None) == "github"

        def is_slack(t) -> bool:
            return (
                getattr(t, "plugin_name", None) == "slack"
                or t.name.startswith("slack_")
            )

        scopes = [
            (("only use github",), is_github),
            (("only use slack",), is_slack),
            (
                (
                    "only use web search",
                    "only use the web",
                    "only use web",
                ),
                lambda t: "web" in t.name.lower(),
            ),
            (
                ("only use memory",),
                lambda t: "memory" in t.name.lower(),
            ),
            (
                ("only use knowledge",),
                lambda t: "knowledge" in t.name.lower(),
            ),
        ]

        selected = []

        for phrases, matcher in scopes:
            if any(p in text for p in phrases):
                for tool in tools:
                    if matcher(tool) and tool not in selected:
                        selected.append(tool)

        return selected

    def definitions_for_prompt(
        self,
        prompt: str,
        max_tools: int = 8,
    ) -> list[ToolDefinition]:
        """
        Return the most relevant tool definitions for a provider request.

        The complete registry remains available for execution. This method
        only limits the tool definitions exposed to the model.
        """

        tools = self.list_tools()

        scoped = self._tools_for_only_use(prompt, tools)

        if scoped:
            tools = scoped

        if len(tools) <= max_tools:
            return [
                ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.parameters,
                )
                for tool in tools
            ]

        def normalize_word(word: str) -> str:
            word = word.strip(
                ".,!?;:()[]{}\"'"
            ).lower()

            if word.endswith("ies") and len(word) > 4:
                return word[:-3] + "y"

            if word.endswith("s") and len(word) > 3:
                return word[:-1]

            return word

        prompt_words = {
            normalize_word(word)
            for word in prompt.split()
            if len(normalize_word(word)) > 2
        }

        # -------------------------------------------------
        # GITHUB / CODEBASE INTENT BOOST
        # -------------------------------------------------
        github_intent_words = {
            "github",
            "repository",
            "repo",
            "codebase",
            "code",
            "project",
            "source",
            "files",
            "file",
            "architecture",
            "readme",
        }

        github_intent = bool(
            prompt_words & github_intent_words
        )

        # -------------------------------------------------
        # KNOWLEDGE / DOCUMENT INTENT BOOST
        # -------------------------------------------------
        knowledge_intent_words = {
            "document",
            "doc",
            "pdf",
            "upload",
            "uploaded",
            "resume",
            "marksheet",
            "notes",
            "percentage",
            "file",
            "certificate",
        }

        knowledge_intent = bool(
            prompt_words & knowledge_intent_words
        )

        github_priority_tools = {
            "search_repositories",
            "search_code",
            "get_file_contents",
            "get_commit",
            "list_branches",
        }

        scored_tools = []

        for index, tool in enumerate(tools):
            tool_words = {
                normalize_word(word)
                for word in (
                    tool.name.replace("_", " ")
                    + " "
                    + tool.description
                ).split()
                if len(normalize_word(word)) > 2
            }

            score = len(
                prompt_words & tool_words
            )

            if (
                github_intent
                and tool.name in github_priority_tools
            ):
                score += 100

            if (
                knowledge_intent
                and not github_intent
                and tool.name == "search_knowledge"
            ):
                score += 100

            scored_tools.append(
                (score, -index, tool)
            )

        scored_tools.sort(
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )

        selected_tools = [
            item[2]
            for item in scored_tools[:max_tools]
        ]

        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
            )
            for tool in selected_tools
        ]
