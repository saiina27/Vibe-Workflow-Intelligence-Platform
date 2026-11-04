import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.ai.tools.base import BaseTool
from app.ai.tools.context import ToolContext
from app.ai.tools.untrusted import NOTICE, WARNING, looks_like_injection
from app.models.code_file import CodeFile
from app.services import code_index_service as cidx

MAX_RESULTS = 8
MAX_CODE_FILES = 2
CACHE_FILES = 40

# File text by (repo, path, sha): the same sha is always the same text.
_FILE_CACHE: "OrderedDict[tuple, str]" = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _cache_get(key):
    with _CACHE_LOCK:
        text = _FILE_CACHE.get(key)

        if text is not None:
            _FILE_CACHE.move_to_end(key)

        return text


def _cache_put(key, text) -> None:
    with _CACHE_LOCK:
        _FILE_CACHE[key] = text
        _FILE_CACHE.move_to_end(key)

        while len(_FILE_CACHE) > CACHE_FILES:
            _FILE_CACHE.popitem(last=False)


class CodeSearchTool(BaseTool):
    """
    Find where something is implemented in the user's tracked
    repositories, using the saved index of function, class and constant
    names, and return the matching lines of the best files.
    Read-only. Scope comes from ToolContext, never from the model: the
    files read are only files that are in the index.
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
            "router or sync. It also returns the matching lines of the best "
            "files in code, so you can usually answer from the result "
            "without reading the file again."
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

    # ------------------------------------------------------------
    # reading files (GitHub MCP connection shared with the chat)
    # ------------------------------------------------------------

    def _fetch(self, repo: str, path: str) -> str | None:
        """File text from GitHub, or None when it cannot be read."""

        try:
            from app.mcp.runtime import mcp_integration_manager

            runtime = mcp_integration_manager._get_github_runtime_name(
                self.context.user_id
            )
            client = mcp_integration_manager.server_manager.get_client(runtime)
            owner, name = repo.split("/", 1)

            result = client.call_tool(
                "get_file_contents",
                {"owner": owner, "repo": name, "path": path},
            )

            return cidx.file_text(result)

        except Exception:
            return None

    def _sha(self, repo: str, path: str) -> str:
        try:
            row = (
                self.context.db.query(CodeFile.sha)
                .filter(
                    CodeFile.workspace_id == self.context.workspace_id,
                    CodeFile.repo == repo,
                    CodeFile.path == path,
                )
                .first()
            )

            return (row[0] if row else "") or ""
        except Exception:
            return ""

    def _file_text(self, repo: str, path: str, sha: str) -> str | None:
        key = (repo, path, sha)

        if sha:
            cached = _cache_get(key)

            if cached is not None:
                return cached

        text = self._fetch(repo, path)

        if text is not None and sha:
            _cache_put(key, text)

        return text

    def _snippets(self, rows, words) -> list[dict]:
        tokens = cidx.tokenize(words)

        targets = []
        seen = set()

        for row in rows:
            key = (row.repo, row.path)

            if key in seen:
                continue

            seen.add(key)
            targets.append(
                (row.repo, row.path, row.line, self._sha(row.repo, row.path))
            )

            if len(targets) == MAX_CODE_FILES:
                break

        def load(target):
            repo, path, _line, sha = target
            return self._file_text(repo, path, sha)

        if len(targets) > 1:
            with ThreadPoolExecutor(max_workers=len(targets)) as pool:
                texts = list(pool.map(load, targets))
        else:
            texts = [load(t) for t in targets]

        out = []

        for index, (target, text) in enumerate(zip(targets, texts)):
            if text is None:
                continue

            limit = cidx.FIRST_FILE_CHARS if index == 0 else cidx.SECOND_FILE_CHARS

            snippet, cut = cidx.keyword_windows(
                text, tokens, limit, fallback_line=target[2]
            )

            if snippet:
                out.append(
                    {
                        "repo": target[0],
                        "path": target[1],
                        "lines": snippet,
                        "truncated": cut,
                    }
                )

        return out

    # ------------------------------------------------------------
    # execution
    # ------------------------------------------------------------

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

        if rows:
            snippets = self._snippets(rows, words)

            if snippets:
                result["code"] = snippets
                result["_notice"] = NOTICE

                if any(looks_like_injection(s["lines"]) for s in snippets):
                    result["_warning"] = WARNING
            else:
                result["code_note"] = (
                    "The code could not be fetched (GitHub is not connected "
                    "or did not respond). Use get_file_contents to read the "
                    "file."
                )

        return result
