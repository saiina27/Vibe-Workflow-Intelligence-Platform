from typing import Any

import requests

from app.ai.tools.base import BaseTool
from app.ai.tools.context import ToolContext
from app.core.config import settings


class WebSearchTool(BaseTool):
    """
    Search the public web for current or external information.

    This tool is intended for information that may change over time,
    including current events, latest software releases, recent
    updates, external facts, and time-sensitive information.

    The LLM controls only the search query.

    API credentials, endpoint, timeout, search depth, and result
    limits remain application-controlled.
    """

    # ========================================================
    # APPLICATION-CONTROLLED LIMITS
    # ========================================================

    MAX_QUERY_CHARS = 1000
    MAX_RESULTS = 5
    MAX_CONTENT_CHARS = 1500
    MAX_ANSWER_CHARS = 3000
    REQUEST_TIMEOUT_SECONDS = 10

    ENDPOINT = "https://api.tavily.com/search"

    def __init__(
        self,
        context: ToolContext,
    ):
        self.context = context

        self.api_key = settings.tavily_api_key

        if not self.api_key:
            raise RuntimeError(
                "TAVILY_API_KEY is not configured."
            )

    # ========================================================
    # TOOL METADATA
    # ========================================================

    @property
    def name(self) -> str:
        return "search_web"

    @property
    def description(self) -> str:
        return (
            "Search the public web for current, latest, "
            "recent, updated, external, or time-sensitive "
            "information. Use this tool when the user asks "
            "about current events, latest software releases, "
            "new features, recent changes, current facts, "
            "or information that may have changed over time. "
            "Prefer this tool over workspace memory or uploaded "
            "knowledge when the user explicitly asks for current "
            "or latest information."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The specific question or topic to search "
                        "for on the public web. Include important "
                        "names, versions, dates, or other details "
                        "needed to identify the correct information."
                    ),
                },
            },
            "required": ["query"],
        }

    # ========================================================
    # QUERY VALIDATION
    # ========================================================

    def _normalize_query(
        self,
        query: str,
    ) -> str:
        """
        Normalize and validate the LLM-provided search query.
        """

        if not isinstance(query, str):
            raise ValueError(
                "Web search query must be a string."
            )

        query = query.strip()

        if not query:
            raise ValueError(
                "Web search query cannot be empty."
            )

        if len(query) > self.MAX_QUERY_CHARS:
            query = query[: self.MAX_QUERY_CHARS].strip()

        return query

    # ========================================================
    # RESULT NORMALIZATION
    # ========================================================

    def _normalize_result(
        self,
        item: Any,
    ) -> dict[str, Any]:
        """
        Convert one Tavily result into a compact,
        provider-friendly representation.
        """

        if not isinstance(item, dict):
            return {
                "title": None,
                "url": None,
                "content": str(item)[: self.MAX_CONTENT_CHARS],
            }

        title = item.get("title")
        url = item.get("url")
        content = item.get("content")

        if title is not None:
            title = str(title)[:500]

        if url is not None:
            url = str(url)[:2000]

        if content is not None:
            content = str(content)[
                : self.MAX_CONTENT_CHARS
            ]

        return {
            "title": title,
            "url": url,
            "content": content,
        }

    # ========================================================
    # EXECUTE SEARCH
    # ========================================================

    def execute(
        self,
        query: str,
    ) -> dict[str, Any]:
        """
        Execute a public web search through Tavily.
        """

        # ====================================================
        # STEP 1: VALIDATE QUERY
        # ====================================================

        try:
            query = self._normalize_query(query)

        except ValueError as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        # ====================================================
        # STEP 2: BUILD APPLICATION-CONTROLLED PAYLOAD
        # ====================================================

        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": self.MAX_RESULTS,
            "include_answer": True,
            "include_raw_content": False,
        }

        # ====================================================
        # STEP 3: CALL TAVILY
        # ====================================================

        try:
            response = requests.post(
                self.ENDPOINT,
                json=payload,
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )

            response.raise_for_status()

        except requests.Timeout:

            return {
                "success": False,
                "query": query,
                "error": (
                    "Web search timed out. "
                    "Please try again."
                ),
            }

        except requests.HTTPError as exc:

            status_code = (
                exc.response.status_code
                if exc.response is not None
                else None
            )

            return {
                "success": False,
                "query": query,
                "error": (
                    "Web search API request failed"
                    + (
                        f" with status {status_code}."
                        if status_code
                        else "."
                    )
                ),
            }

        except requests.RequestException:

            return {
                "success": False,
                "query": query,
                "error": (
                    "Unable to reach the web search service."
                ),
            }

        # ====================================================
        # STEP 4: PARSE RESPONSE
        # ====================================================

        try:
            data = response.json()

        except ValueError:

            return {
                "success": False,
                "query": query,
                "error": (
                    "Web search service returned "
                    "an invalid response."
                ),
            }

        if not isinstance(data, dict):

            return {
                "success": False,
                "query": query,
                "error": (
                    "Web search service returned "
                    "an unexpected response."
                ),
            }

        # ====================================================
        # STEP 5: NORMALIZE RESULTS
        # ====================================================

        raw_results = data.get(
            "results",
            [],
        )

        if not isinstance(
            raw_results,
            list,
        ):
            raw_results = []

        results = [
            self._normalize_result(item)
            for item in raw_results[
                : self.MAX_RESULTS
            ]
        ]

        # ====================================================
        # STEP 6: NORMALIZE ANSWER
        # ====================================================

        answer = data.get("answer")

        if answer is not None:
            answer = str(answer)[
                : self.MAX_ANSWER_CHARS
            ]

        # ====================================================
        # STEP 7: RETURN COMPACT TOOL RESULT
        # ====================================================

        return {
            "success": True,
            "query": query,
            "answer": answer,
            "count": len(results),
            "results": results,
        }