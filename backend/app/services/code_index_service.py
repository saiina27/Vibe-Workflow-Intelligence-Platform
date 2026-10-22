import ast
import re
import time
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.ai.tools.result_compactor import to_plain
from app.models.code_file import CodeFile, CodeSymbol
from app.services import dev_events_service as dev

MAX_ATTEMPTS = 3
MAX_FILES = 400
MAX_DIRS = 120
MAX_FILE_BYTES = 150_000
MAX_SYMBOLS_PER_FILE = 300
BATCH_SECONDS = 40
SAFETY_MARGIN = 3

# A folder is stored as a CodeFile row with this size. indexed_sha is
# NULL while the folder still has to be listed and DIR_DONE afterwards.
DIR_SIZE = -1
DIR_DONE = "dir"

SKIP_DIRS = {
    "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    "site-packages", "uploads", "migrations", "frontend", "docs",
    "public", "assets", "static",
}

HTTP_METHODS = {"get", "post", "put", "delete", "patch"}

STOPWORDS = {
    "the", "and", "how", "does", "work", "works", "for", "with", "this",
    "that", "what", "where", "which", "code", "file", "files",
}


# ------------------------------------------------------------
# Parsing (no LLM, no code stored)
# ------------------------------------------------------------

def _first_line(text: str | None) -> str:
    for line in (text or "").strip().splitlines():
        line = line.strip()

        if line:
            return line[:160]

    return ""


def _route_doc(node: Any) -> str | None:
    for dec in getattr(node, "decorator_list", []):
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and dec.func.attr in HTTP_METHODS
            and dec.args
            and isinstance(dec.args[0], ast.Constant)
            and isinstance(dec.args[0].value, str)
        ):
            return f"{dec.func.attr.upper()} {dec.args[0].value}"

    return None


def _doc(node: Any) -> str:
    parts = [_route_doc(node), _first_line(ast.get_docstring(node))]

    return " · ".join(p for p in parts if p)


def _is_constant(name: str) -> bool:
    return len(name) >= 3 and name.isupper() and not name.startswith("__")


def _symbol(name, qualname, kind, line, doc) -> dict:
    return {
        "name": name[:200],
        "qualname": qualname[:300],
        "kind": kind,
        "line": int(line),
        "doc": (doc or "")[:200] or None,
    }


_REGEX = re.compile(r"^([ \t]*)(?:async[ \t]+)?(class|def)[ \t]+([A-Za-z_]\w*)", re.M)


def _regex_symbols(source: str) -> list[dict]:
    """Fallback for files `ast` cannot parse."""

    out = []

    for match in _REGEX.finditer(source):
        indent, word, name = match.groups()
        line = source.count("\n", 0, match.start()) + 1

        if word == "class":
            kind = "class"
        else:
            kind = "method" if indent else "function"

        out.append(_symbol(name, name, kind, line, None))

        if len(out) >= MAX_SYMBOLS_PER_FILE:
            break

    return out


def parse_symbols(source: str) -> list[dict]:
    """Top-level classes, functions, methods and constants of a file."""

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return _regex_symbols(source)

    out: list[dict] = []
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out.append(
                _symbol(
                    node.name, node.name, "class", node.lineno,
                    _first_line(ast.get_docstring(node)),
                )
            )

            for child in node.body:
                if isinstance(child, functions):
                    out.append(
                        _symbol(
                            child.name,
                            f"{node.name}.{child.name}",
                            "method",
                            child.lineno,
                            _doc(child),
                        )
                    )

        elif isinstance(node, functions):
            out.append(
                _symbol(node.name, node.name, "function", node.lineno, _doc(node))
            )

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and _is_constant(target.id):
                    out.append(
                        _symbol(target.id, target.id, "constant", node.lineno, None)
                    )

        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and _is_constant(node.target.id)
        ):
            out.append(
                _symbol(
                    node.target.id, node.target.id, "constant", node.lineno, None
                )
            )

        if len(out) >= MAX_SYMBOLS_PER_FILE:
            break

    return out[:MAX_SYMBOLS_PER_FILE]


# ------------------------------------------------------------
# Reading GitHub results
# ------------------------------------------------------------

def file_text(result: Any) -> str | None:
    """Text of get_file_contents for a file (a `resource` block)."""

    plain = to_plain(result)

    if isinstance(plain, dict) and "content" not in plain and "data" in plain:
        plain = to_plain(plain["data"])

    if not isinstance(plain, dict):
        return None

    if plain.get("is_error") or plain.get("isError"):
        raise RuntimeError("GitHub tool returned an error.")

    for block in plain.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "resource":
            resource = block.get("resource") or {}

            if isinstance(resource.get("text"), str):
                return resource["text"]

    return None


def list_dir(call: Callable, owner: str, name: str, path: str) -> list[dict]:
    attempts = [path] if path else ["/", ""]

    for candidate in attempts:
        text = dev.result_text(
            call(
                "get_file_contents",
                {"owner": owner, "repo": name, "path": candidate},
            )
        )
        entries = dev.parse_json_list(text)

        if entries:
            return [e for e in entries if isinstance(e, dict)]

    return []


def _skip_dir(path: str) -> bool:
    parts = path.split("/")

    if any(p in SKIP_DIRS or p.startswith(".") for p in parts):
        return True

    return "alembic/versions" in path


def _wanted_file(path: str, size: Any) -> bool:
    try:
        size = int(size or 0)
    except (TypeError, ValueError):
        return False

    return path.endswith(".py") and 0 < size <= MAX_FILE_BYTES


def _parent(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


# ------------------------------------------------------------
# Work budget (time, and optionally a number of GitHub calls)
# ------------------------------------------------------------

class _Budget:
    def __init__(self, seconds: float, calls: int | None = None):
        self.deadline = time.monotonic() + seconds
        self.calls = calls

    def ok(self) -> bool:
        if time.monotonic() >= self.deadline - SAFETY_MARGIN:
            return False

        return self.calls is None or self.calls > 0

    def spend(self) -> None:
        if self.calls is not None:
            self.calls -= 1


# ------------------------------------------------------------
# Row filters
# ------------------------------------------------------------

def _pending_filter():
    return and_(
        CodeFile.size >= 0,
        CodeFile.attempts < MAX_ATTEMPTS,
        or_(
            CodeFile.indexed_sha.is_(None),
            CodeFile.indexed_sha != CodeFile.sha,
        ),
    )


def _pending_dir_filter():
    return and_(
        CodeFile.size == DIR_SIZE,
        CodeFile.attempts < MAX_ATTEMPTS,
        CodeFile.indexed_sha.is_(None),
    )


def _scope(workspace_id: int, repo: str):
    return (CodeFile.workspace_id == workspace_id, CodeFile.repo == repo)


def _prefix_like(path: str) -> str:
    escaped = path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    return f"{escaped}/%"


# ------------------------------------------------------------
# Scan (resumable) and index
# ------------------------------------------------------------

def restart_scan(db: Session, workspace_id: int, repo: str) -> None:
    """Mark every saved folder as not listed yet and make sure the root exists."""

    db.query(CodeFile).filter(
        *_scope(workspace_id, repo), CodeFile.size == DIR_SIZE
    ).update(
        {"indexed_sha": None, "attempts": 0, "error": None},
        synchronize_session=False,
    )

    root = (
        db.query(CodeFile.id)
        .filter(*_scope(workspace_id, repo), CodeFile.path == "", CodeFile.size == DIR_SIZE)
        .first()
    )

    if root is None:
        db.add(
            CodeFile(
                workspace_id=workspace_id, repo=repo, path="",
                sha="", size=DIR_SIZE, attempts=0,
            )
        )

    db.commit()


def _delete_subtree(db: Session, workspace_id: int, repo: str, path: str) -> None:
    ids = [
        r[0]
        for r in db.query(CodeFile.id)
        .filter(
            *_scope(workspace_id, repo),
            or_(CodeFile.path == path, CodeFile.path.like(_prefix_like(path), escape="\\")),
        )
        .all()
    ]

    if not ids:
        return

    db.query(CodeSymbol).filter(CodeSymbol.file_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.query(CodeFile).filter(CodeFile.id.in_(ids)).delete(
        synchronize_session=False
    )


def _apply_directory(
    db: Session, workspace_id: int, repo: str, path: str, entries: list[dict]
) -> None:
    """Save what one folder contains: files to index and folders to visit."""

    existing = {
        r.path: r
        for r in db.query(CodeFile).filter(*_scope(workspace_id, repo)).all()
        if r.path and _parent(r.path) == path
    }

    dir_count = (
        db.query(func.count(CodeFile.id))
        .filter(*_scope(workspace_id, repo), CodeFile.size == DIR_SIZE)
        .scalar()
        or 0
    )

    seen: set[str] = set()

    for entry in entries:
        entry_path = entry.get("path")
        kind = entry.get("type")

        if not isinstance(entry_path, str) or _parent(entry_path) != path:
            continue

        if kind == "dir":
            if _skip_dir(entry_path):
                continue

            seen.add(entry_path)

            if entry_path not in existing:
                dir_count += 1

                if dir_count > MAX_DIRS:
                    raise RuntimeError(
                        "Repository has too many folders for the code index."
                    )

                db.add(
                    CodeFile(
                        workspace_id=workspace_id, repo=repo, path=entry_path,
                        sha="", size=DIR_SIZE, attempts=0,
                    )
                )

        elif kind == "file" and _wanted_file(entry_path, entry.get("size")):
            seen.add(entry_path)
            sha = str(entry.get("sha") or "")
            size = int(entry.get("size") or 0)
            row = existing.get(entry_path)

            if row is None:
                db.add(
                    CodeFile(
                        workspace_id=workspace_id, repo=repo, path=entry_path,
                        sha=sha, size=size, attempts=0,
                    )
                )
            elif row.size == DIR_SIZE:
                row.sha = sha
                row.size = size
                row.indexed_sha = None
                row.attempts = 0
            elif row.sha != sha or row.size != size:
                row.sha = sha
                row.size = size
                row.attempts = 0

    for child_path in list(existing):
        if child_path not in seen:
            _delete_subtree(db, workspace_id, repo, child_path)

    db.commit()

    files = (
        db.query(func.count(CodeFile.id))
        .filter(*_scope(workspace_id, repo), CodeFile.size >= 0)
        .scalar()
        or 0
    )

    if files > MAX_FILES:
        raise RuntimeError("Repository has too many files for the code index.")


def scan_some(
    db: Session, workspace_id: int, repo: str, call: Callable, budget: _Budget
) -> int:
    """List as many pending folders as the budget allows. Progress is saved."""

    owner, name = repo.split("/", 1)
    scanned = 0

    while budget.ok():
        row = (
            db.query(CodeFile)
            .filter(*_scope(workspace_id, repo), _pending_dir_filter())
            .order_by(CodeFile.path)
            .first()
        )

        if row is None:
            break

        row_id, path = row.id, row.path
        budget.spend()

        try:
            entries = list_dir(call, owner, name, path)
        except Exception as exc:
            db.rollback()
            failed = db.get(CodeFile, row_id)

            if failed is not None:
                failed.attempts = (failed.attempts or 0) + 1
                failed.error = str(exc)[:200]
                db.commit()

            continue

        if path == "" and not entries:
            raise RuntimeError("Could not list the repository root.")

        _apply_directory(db, workspace_id, repo, path, entries)

        done = db.get(CodeFile, row_id)

        if done is not None:
            done.indexed_sha = DIR_DONE
            done.attempts = 0
            done.error = None
            db.commit()

        scanned += 1

    return scanned


def index_file(db: Session, code_file: CodeFile, text: str) -> int:
    symbols = parse_symbols(text)

    db.query(CodeSymbol).filter(CodeSymbol.file_id == code_file.id).delete()

    for symbol in symbols:
        db.add(
            CodeSymbol(
                file_id=code_file.id,
                workspace_id=code_file.workspace_id,
                repo=code_file.repo,
                path=code_file.path,
                **symbol,
            )
        )

    code_file.indexed_sha = code_file.sha
    code_file.indexed_at = datetime.utcnow()
    code_file.attempts = 0
    code_file.error = None

    db.commit()

    return len(symbols)


def index_status(db: Session, workspace_id: int, repo: str) -> dict:
    scope = _scope(workspace_id, repo)

    files = (
        db.query(func.count(CodeFile.id))
        .filter(*scope, CodeFile.size >= 0)
        .scalar()
        or 0
    )
    indexed = (
        db.query(func.count(CodeFile.id))
        .filter(*scope, CodeFile.size >= 0, CodeFile.indexed_sha == CodeFile.sha)
        .scalar()
        or 0
    )
    pending = (
        db.query(func.count(CodeFile.id)).filter(*scope, _pending_filter()).scalar()
        or 0
    )
    dirs_left = (
        db.query(func.count(CodeFile.id))
        .filter(*scope, _pending_dir_filter())
        .scalar()
        or 0
    )
    symbols = (
        db.query(func.count(CodeSymbol.id))
        .filter(CodeSymbol.workspace_id == workspace_id, CodeSymbol.repo == repo)
        .scalar()
        or 0
    )
    last = (
        db.query(func.max(CodeFile.indexed_at))
        .filter(*scope, CodeFile.size >= 0)
        .scalar()
    )

    return {
        "repo": repo,
        "files": files,
        "indexed": indexed,
        "pending": pending,
        "dirs_left": dirs_left,
        "symbols": symbols,
        "last_indexed_at": last,
    }


def run_batch(
    db: Session,
    workspace_id: int,
    repo: str,
    call: Callable,
    scan: bool = False,
    budget_seconds: float = BATCH_SECONDS,
    max_calls: int | None = None,
) -> dict:
    """
    One batch of work: list pending folders, then index pending files.
    Press again until `done`. Progress is saved after every step.
    """

    if not dev.is_valid_repo(repo):
        raise ValueError("Repository must look like owner/repo.")

    budget = _Budget(budget_seconds, max_calls)
    owner, name = repo.split("/", 1)

    has_rows = (
        db.query(func.count(CodeFile.id))
        .filter(*_scope(workspace_id, repo))
        .scalar()
        or 0
    )

    if scan or not has_rows:
        restart_scan(db, workspace_id, repo)

    scanned = scan_some(db, workspace_id, repo, call, budget)

    dirs_left = (
        db.query(func.count(CodeFile.id))
        .filter(*_scope(workspace_id, repo), _pending_dir_filter())
        .scalar()
        or 0
    )

    processed = 0
    errors = 0

    if dirs_left == 0:
        pending_rows = (
            db.query(CodeFile)
            .filter(*_scope(workspace_id, repo), _pending_filter())
            .order_by(CodeFile.path)
            .limit(300)
            .all()
        )

        for row in pending_rows:
            if not budget.ok():
                break

            row_id, path = row.id, row.path
            budget.spend()

            try:
                text = file_text(
                    call(
                        "get_file_contents",
                        {"owner": owner, "repo": name, "path": path},
                    )
                )

                if text is None:
                    raise RuntimeError("No text content")

                index_file(db, row, text)
                processed += 1

            except Exception as exc:
                db.rollback()
                failed = db.get(CodeFile, row_id)

                if failed is not None:
                    failed.attempts = (failed.attempts or 0) + 1
                    failed.error = str(exc)[:200]
                    db.commit()

                errors += 1

    status = index_status(db, workspace_id, repo)

    return {
        **status,
        "scanned": scanned,
        "processed": processed,
        "errors": errors,
        "done": (
            status["files"] > 0
            and status["pending"] == 0
            and status["dirs_left"] == 0
        ),
    }


def delete_repo_index(db: Session, workspace_id: int, repo: str) -> None:
    db.query(CodeSymbol).filter(
        CodeSymbol.workspace_id == workspace_id, CodeSymbol.repo == repo
    ).delete()
    db.query(CodeFile).filter(*_scope(workspace_id, repo)).delete()
    db.commit()


# ------------------------------------------------------------
# Search
# ------------------------------------------------------------

def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def tokenize(keywords: list[str] | None) -> list[str]:
    tokens: list[str] = []

    for keyword in keywords or []:
        for token in re.findall(r"[A-Za-z0-9]+", str(keyword).lower()):
            if len(token) >= 3 and token not in STOPWORDS and token not in tokens:
                tokens.append(token)

    return tokens[:6]


def _is_test_path(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]

    return "/tests/" in f"/{path}" or base.startswith("test_")


def search_symbols(
    db: Session,
    workspace_id: int,
    keywords: list[str] | None,
    repo: str | None = None,
    limit: int = 8,
) -> list[CodeSymbol]:
    tokens = tokenize(keywords)

    if not tokens:
        return []

    clauses = []

    for token in tokens:
        like = _like(token)
        clauses += [
            CodeSymbol.name.ilike(like, escape="\\"),
            CodeSymbol.qualname.ilike(like, escape="\\"),
            CodeSymbol.doc.ilike(like, escape="\\"),
            CodeSymbol.path.ilike(like, escape="\\"),
        ]

    query = db.query(CodeSymbol).filter(
        CodeSymbol.workspace_id == workspace_id, or_(*clauses)
    )

    if repo:
        query = query.filter(CodeSymbol.repo.ilike(_like(repo), escape="\\"))

    rows = query.limit(500).all()

    def score(row: CodeSymbol) -> float:
        qual = row.qualname.lower()
        name = row.name.lower()
        doc = (row.doc or "").lower()
        path = row.path.lower()

        total = 0.0
        matched = 0

        for token in tokens:
            hit = False

            if token in qual:
                total += 4
                hit = True

                if token in name:
                    total += 2

            if token in doc:
                total += 2
                hit = True

            if token in path:
                total += 1
                hit = True

            matched += 1 if hit else 0

        total += matched * 3

        if _is_test_path(row.path):
            total -= 4

        if row.kind in ("class", "function", "method"):
            total += 1

        return total

    ranked = sorted(rows, key=lambda r: (-score(r), r.path, r.line))

    return ranked[: max(1, min(limit, 20))]


def workspace_index_counts(db: Session, workspace_id: int) -> dict:
    files = (
        db.query(func.count(CodeFile.id))
        .filter(CodeFile.workspace_id == workspace_id, CodeFile.size >= 0)
        .scalar()
        or 0
    )
    pending = (
        db.query(func.count(CodeFile.id))
        .filter(CodeFile.workspace_id == workspace_id, _pending_filter())
        .scalar()
        or 0
    )
    symbols = (
        db.query(func.count(CodeSymbol.id))
        .filter(CodeSymbol.workspace_id == workspace_id)
        .scalar()
        or 0
    )

    return {"files": files, "pending": pending, "symbols": symbols}
