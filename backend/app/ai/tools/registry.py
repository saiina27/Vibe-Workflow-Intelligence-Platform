import copy
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
GITHUB_ISSUE_TOOLS = {
    "get_me",
    "list_issues",
    "issue_read",
    "search_issues",
    "search_repositories",
}
GITHUB_SEARCH_TOOLS = {"get_me", "search_repositories", "search_code"}
GITHUB_RELEASE_TOOLS = {
    "get_me",
    "list_releases",
    "get_latest_release",
    "list_tags",
    "get_release_by_tag",
}
GITHUB_PR_DETAIL_TOOLS = {"get_me", "list_pull_requests", "pull_request_read"}

# Max tools exposed to the model per request (Groq token budget).
MAX_EXPOSED_TOOLS = 12

# Words that suggest the user means an earlier Vibe chat.
CHAT_INTENT_WORDS = {
    "chat", "chats", "conversation", "conversations",
    "earlier", "previous", "yesterday",
}

# Words that suggest the user wants saved development history.
HISTORY_INTENT_WORDS = {
    "history", "activity", "timeline", "happened", "changed", "changes",
    "week", "yesterday", "today", "past",
    # existence questions ("was there ever a commit about X?")
    "ever", "mention", "mentions", "mentioned",
    "hua", "hue", "hui", "tha", "thi", "kiya", "kiye",
}

# Words and dates that point to a past period ("last week", "5 Oct").
PAST_PERIOD_WORDS = {
    "week", "weeks", "yesterday", "month", "months", "ago", "earlier",
}

_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
    r"aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)

_DATE_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}\s*" + _MONTH + r"\b"
    r"|\b" + _MONTH + r"\s*\d{1,2}\b"
)


def _is_past_period_question(text: str, words: set) -> bool:
    return bool(words & PAST_PERIOD_WORDS) or bool(_DATE_PATTERN.search(text))


# Words that suggest the answer may live in Slack (team messages).
SLACK_INTENT_WORDS = {
    "slack", "channel", "channels", "team", "teammates", "discussion",
    "discussed", "message", "messages", "thread", "threads", "query",
    "queries", "update", "updates", "decided", "decision",
    "announcement", "announcements",
}

# Write/mutating GitHub tools. These are NEVER exposed to the model
# and NEVER executed (see ToolCallingService).
BLOCKED_WRITE_PREFIXES = (
    "create_",
    "update_",
    "delete_",
    "push_",
    "merge_",
    "fork_",
    "add_",
    "request_",
    "run_",
)
BLOCKED_WRITE_SUFFIXES = ("_write",)


def is_blocked_write_tool(name: str) -> bool:
    """
    True for any GitHub write/mutating tool name. Read tools
    (get_*, list_*, search_*, issue_read, pull_request_read) pass.
    """

    if not name:
        return False

    lowered = name.lower()

    return lowered.startswith(BLOCKED_WRITE_PREFIXES) or lowered.endswith(
        BLOCKED_WRITE_SUFFIXES
    )


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
    def _model_parameters(tool):
        """
        Parameters shown to the model. get_file_contents has an
        optional `fields` array whose allowed values only fit
        directory listings; the model sometimes sends invalid values
        and the provider rejects the whole request. Hide it so file
        reads use the plain path (owner, repo, path).
        """

        params = tool.parameters

        if tool.name != "get_file_contents" or not isinstance(params, dict):
            return params

        cleaned = copy.deepcopy(params)

        props = cleaned.get("properties")
        if isinstance(props, dict):
            props.pop("fields", None)

        required = cleaned.get("required")
        if isinstance(required, list) and "fields" in required:
            cleaned["required"] = [r for r in required if r != "fields"]

        return cleaned

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
    def _intent_text(prompt: str) -> str:
        """
        Text used to detect intent: the latest user message. If it is
        a very short follow-up (for example just "vibe" after "which
        repo?"), the previous user message is included as well.
        """

        latest = ToolRegistry._latest_user_text(prompt)

        if len(latest.split()) > 3:
            return latest

        text = prompt
        marker = "CURRENT CONVERSATION"

        if marker in text:
            text = text.rsplit(marker, 1)[1]

        end = text.find("RESPONSE INSTRUCTION")

        if end != -1:
            text = text[:end]

        chunks = text.split("\nUser:")

        if len(chunks) >= 3:
            previous = chunks[-2].split("\nAssistant:")[0]
            return (previous + " " + latest).strip()

        return latest

    @staticmethod
    def _is_github_intent(prompt: str) -> bool:
        """
        Decide GitHub intent from the user's latest message only
        (the full prompt always contains the word "GitHub" in the
        system instructions). Generic words like release/tag/bug
        count only together with ownership words (my/mine/our).
        """

        text = ToolRegistry._intent_text(prompt).lower()
        words = set(re.findall(r"[a-z0-9]+", text))

        strong = {
            "github", "repo", "repos", "repository", "repositories",
            "commit", "commits", "branch", "branches", "readme",
            "pr", "prs",
        }

        if words & strong or "pull request" in text:
            return True

        weak = {
            "issue", "issues", "bug", "bugs", "release", "releases",
            "tag", "tags", "changelog",
        }
        owner = {"my", "mine", "our"}

        if words & weak and words & owner:
            return True

        # "any update / progress on my project (or Vibe)" -> GitHub activity
        activity = {
            "update", "updates", "changes", "changed", "activity",
            "progress", "latest", "recent",
        }
        about_project = "vibe" in words or bool(
            words & {"project", "projects"} and words & owner
        )

        return bool(words & activity and about_project)

    @staticmethod
    def _github_allowed_tools(prompt: str) -> set[str]:
        """
        Pick ONE read-only GitHub tool group by prompt intent
        (priority: PR detail > issues > releases/tags > search >
        default), plus the core Vibe tools. One group per prompt
        keeps the request under Groq's 8000 TPM limit.
        """

        text = ToolRegistry._intent_text(prompt).lower()
        words = set(re.findall(r"[a-z0-9]+", text))

        pr_detail = (
            "files changed" in text
            or "changed files" in text
            or bool(words & {"review", "reviews", "reviewer", "reviewers"})
            or re.search(r"\b(pr|pull request)\s*#?\d+", text) is not None
        )

        # Collect every matching group (in priority order) so a
        # multi-topic question gets all the tools it needs, but stop
        # adding groups once the exposed set would exceed the budget.
        matched = []

        if pr_detail:
            matched.append(GITHUB_PR_DETAIL_TOOLS)

        if words & {"issue", "issues", "bug", "bugs"}:
            matched.append(GITHUB_ISSUE_TOOLS)

        if words & {
            "release", "releases", "tag", "tags",
            "version", "versions", "changelog",
        }:
            matched.append(GITHUB_RELEASE_TOOLS)

        if words & {"search", "find"} and words & {
            "repo", "repos", "repository", "repositories", "code",
        }:
            matched.append(GITHUB_SEARCH_TOOLS)

        if not matched:
            matched.append(GITHUB_DEFAULT_READ_TOOLS)

        allowed = set(CORE_TOOLS) | set(matched[0])

        for extra in matched[1:]:
            if len(allowed | set(extra)) <= MAX_EXPOSED_TOOLS:
                allowed |= set(extra)

        # Mixed GitHub + Slack question: add one read-only Slack search
        # tool if it still fits the token budget.
        if words & SLACK_INTENT_WORDS and len(allowed) + 1 <= MAX_EXPOSED_TOOLS:
            allowed.add("slack_search_public")

        if words & CHAT_INTENT_WORDS and len(allowed) + 1 <= MAX_EXPOSED_TOOLS:
            allowed.add("search_chats")

        past_period = _is_past_period_question(text, words)

        if (
            words & HISTORY_INTENT_WORDS or past_period
        ) and len(allowed) + 1 <= MAX_EXPOSED_TOOLS:
            allowed.add("search_history")

        # Past-period questions are answered from saved history, so the
        # live list tools are hidden (they cost many tokens and rounds).
        if past_period and "search_history" in allowed:
            allowed -= {"list_commits", "list_pull_requests"}

        return allowed

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

        # Hard block: write tools are never candidates, for any prompt.
        tools = [
            tool
            for tool in self.list_tools()
            if not is_blocked_write_tool(tool.name)
        ]

        scoped = self._tools_for_only_use(prompt, tools)

        if scoped:
            tools = scoped

        # GitHub repo/commit prompts: expose a small, fixed set of
        # read-only GitHub tools plus the core Vibe tools (web,
        # knowledge, memory). Keeps the request under Groq's token
        # limit and never exposes GitHub write tools.
        if self._is_github_intent(prompt):
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
                        parameters=self._model_parameters(tool),
                    )
                    for tool in selected
                ]

        # Non-GitHub prompts (PDF, memory, web, Slack): expose the fixed
        # core tools plus Slack tools. GitHub tools stay hidden unless
        # the latest message has GitHub intent.
        if not scoped:
            fixed = [
                tool
                for tool in tools
                if tool.name in CORE_TOOLS
                or tool.name == "search_chats"
                or tool.name == "search_history"
                or getattr(tool, "plugin_name", None) == "slack"
                or tool.name.startswith("slack_")
            ]

            if fixed:
                return [
                    ToolDefinition(
                        name=tool.name,
                        description=tool.description,
                        parameters=tool.parameters,
                    )
                    for tool in fixed
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
