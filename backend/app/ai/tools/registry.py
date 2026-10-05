import re

from app.ai.tools.base import BaseTool
from app.schemas.ai import ToolDefinition

CORE_TOOLS = {"search_web", "search_knowledge", "search_memory"}

# Sirf read-only GitHub tools. Write tools yahan kabhi nahi aayenge.
GITHUB_DEFAULT_READ_TOOLS = {
    "get_me",
    "list_commits",
    "get_commit",
    "list_branches",
    "get_file_contents",
    "list_pull_requests",
    "search_repositories",
}
GITHUB_ISSUE_TOOLS = {"get_me", "list_issues", "issue_read", "search_issues"}
GITHUB_SEARCH_TOOLS = {"get_me", "search_repositories", "search_code"}
GITHUB_RELEASE_TOOLS = {
    "get_me",
    "list_releases",
    "get_latest_release",
    "list_tags",
    "get_release_by_tag",
}
GITHUB_PR_DETAIL_TOOLS = {"get_me", "list_pull_requests", "pull_request_read"}


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
    def _latest_user_text(prompt: str) -> str:
        """
        The prompt sent to the gateway also contains the long
        system instructions and the whole chat history. Intent
        must be detected only from the user's latest message.
        """

        text = prompt
        marker = "CURRENT CONVERSATION"

        if marker in text:
            text = text.rsplit(marker, 1)[1]

        end = text.find("RESPONSE INSTRUCTION")

        if end != -1:
            text = text[:end]

        start = text.rfind("\nUser:")

        if start != -1:
            text = text[start + len("\nUser:"):]

        return text.strip(" =\n")

    @staticmethod
    def _github_allowed_tools(prompt: str) -> set[str]:
        """
        Pick ONE read-only GitHub tool group by prompt intent
        (priority: PR detail > issues > releases/tags > search >
        default), plus the core Vibe tools. One group per prompt
        keeps the request under Groq's 8000 TPM limit.
        """

        text = ToolRegistry._latest_user_text(prompt).lower()
        words = set(re.findall(r"[a-z0-9]+", text))

        pr_detail = (
            "files changed" in text
            or "changed files" in text
            or bool(words & {"review", "reviews", "reviewer", "reviewers"})
            or re.search(r"\b(pr|pull request)\s*#?\d+", text) is not None
        )

        if pr_detail:
            group = GITHUB_PR_DETAIL_TOOLS
        elif words & {"issue", "issues", "bug", "bugs"}:
            group = GITHUB_ISSUE_TOOLS
        elif words & {
            "release", "releases", "tag", "tags",
            "version", "versions", "changelog",
        }:
            group = GITHUB_RELEASE_TOOLS
        elif words & {"search", "find"} and words & {
            "repo", "repos", "repository", "repositories", "code",
        }:
            group = GITHUB_SEARCH_TOOLS
        else:
            group = GITHUB_DEFAULT_READ_TOOLS

        return group | CORE_TOOLS

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

        # GitHub repo/commit prompts: expose a small, fixed set of
        # read-only GitHub tools plus the core Vibe tools (web,
        # knowledge, memory). Keeps the request under Groq's token
        # limit and never exposes GitHub write tools.
        github_words = ("github", "repo", "commit", "branch")

        if any(word in prompt.lower() for word in github_words):
            allowed = self._github_allowed_tools(prompt)

            selected = [
                tool
                for tool in tools
                if tool.name in allowed
            ]

            if selected:
                return [
                    ToolDefinition(
                        name=tool.name,
                        description=tool.description,
                        parameters=tool.parameters,
                    )
                    for tool in selected
                ]

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
            "commit",
            "branch",
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

        # -------------------------------------------------
        # MEMORY INTENT BOOST
        # -------------------------------------------------
        memory_intent_words = {
            "remember",
            "recall",
            "memory",
            "memories",
            "remembered",
            "forgot",
            "forget",
            "stored",
            "saved",
        }

        memory_intent = bool(
            prompt_words & memory_intent_words
        )

        # -------------------------------------------------
        # WEB / CURRENT INFORMATION INTENT BOOST
        # -------------------------------------------------
        web_intent_words = {
            "latest",
            "current",
            "recent",
            "newest",
            "updated",
            "today",
            "recently",
            "release",
            "released",
            "version",
            "news",
            "current",
            "online",
            "internet",
            "web",
        }

        web_intent = bool(
            prompt_words & web_intent_words
        )

        # "latest commits in my repo" is a GitHub request,
        # not a web search. Strong GitHub words win over
        # generic recency words like "latest" / "recent".
        strong_github_intent = bool(
            prompt_words
            & {"github", "repo", "repository", "commit", "branch"}
        )

        if strong_github_intent:
            web_intent = False

        github_priority_tools = {
            "search_repositories",
            "search_code",
            "get_file_contents",
            "get_commit",
            "list_branches",
            "list_commits",
            "list_pull_requests",
            "list_issues",
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

            # Explicit intent priority:
            # Knowledge > Memory > Web > GitHub
            #
            # Once a higher-priority intent is detected, lower-priority
            # tool boosts must not compete with it.

            if (
                github_intent
                and not knowledge_intent
                and not memory_intent
                and not web_intent
                and tool.name in github_priority_tools
            ):
                score += 100

            if (
                knowledge_intent
                and tool.name == "search_knowledge"
            ):
                score += 100

            if (
                memory_intent
                and not knowledge_intent
                and tool.name == "search_memory"
            ):
                score += 100

            if (
                web_intent
                and not knowledge_intent
                and not memory_intent
                and tool.name == "search_web"
                and tool.name == "search_web"
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
