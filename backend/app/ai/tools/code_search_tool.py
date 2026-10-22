from typing import Any

from app.ai.tools.base import BaseTool
from app.ai.tools.context import ToolContext
from app.services import code_index_service as cidx

MAX_RESULTS = 8


class CodeSearchTool(BaseTool):
    """
    Find where something is implemented in the user's tracked
    repositories, using the saved index of function, class and constant
    names. Read-only. Scope comes from ToolContext, never from the model.
    """

    def __init__(self, context: ToolContext):
        self.context = context

    @property
    def name(self) -> str:
        return "find_in_code"

    @property
    def description(self) -> str:
        return (
            "Find where something is implemented in the user's tracked "
            "repositories. Searches a saved index of function, class and "
            "constant names (not code text) and returns file paths with "
            "line numbers. Use identifier or topic words such as cooldown, "
            "router or sync. Then read the file with get_file_contents."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": "Up to 5 identifier or topic words.",
                },
                "query": {
                    "type": ["string", "null"],
                    "description": "Alternative to keywords: a short phrase.",
                },
                "repo": {
                    "type": ["string", "null"],
                    "description": "Optional repository (or part of its name).",
                },
            },
            "required": [],
        }

    def execute(
        self,
        keywords: Any = None,
        query: Any = None,
        repo: Any = None,
        **_ignored: Any,
    ) -> dict[str, Any]:

        words: list[str] = []

        if isinstance(keywords, str):
            words.append(keywords)
        elif isinstance(keywords, (list, tuple)):
            words.extend(str(k) for k in keywords)

        if isinstance(query, str) and query.strip():
            words.append(query)

        if not cidx.tokenize(words):
            return {
                "success": False,
                "error": "Give keywords such as an identifier or topic word.",
            }

        counts = cidx.workspace_index_counts(
            self.context.db, self.context.workspace_id
        )

        rows = cidx.search_symbols(
            self.context.db,
            self.context.workspace_id,
            words,
            repo=str(repo).strip() if repo else None,
            limit=MAX_RESULTS,
        )

        result: dict[str, Any] = {
            "success": True,
            "count": len(rows),
            "matches": [
                {
                    "repo": r.repo,
                    "path": r.path,
                    "line": r.line,
                    "symbol": r.qualname,
                    "kind": r.kind,
                    "doc": r.doc,
                }
                for r in rows
            ],
            "indexed_files": counts["files"] - counts["pending"],
        }

        if counts["symbols"] == 0:
            result["note"] = (
                "The code index is empty. Ask the user to open Activity "
                "and press Index code."
            )
        elif counts["pending"] > 0:
            result["note"] = (
                f"The index is partial: {counts['pending']} files are not "
                "indexed yet."
            )
        elif not rows:
            result["note"] = (
                "No symbol matched. Try other keywords (an identifier or "
                "a topic word)."
            )

        return result
