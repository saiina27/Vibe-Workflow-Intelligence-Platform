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
MAX_DIRS = 80
MAX_FILE_BYTES = 150_000
MAX_SYMBOLS_PER_FILE = 300
BATCH_SECONDS = 40
SAFETY_MARGIN = 3

SKIP_DIRS = {
    "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    "site-packages", "uploads", "migrations",
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


# ------------------------------------------------------------
# Scan, index, status
# ------------------------------------------------------------

def _pending_filter():
    return and_(
        CodeFile.attempts < MAX_ATTEMPTS,
        or_(
            CodeFile.indexed_sha.is_(None),
            CodeFile.indexed_sha != CodeFile.sha,
        ),
    )


def scan_repo(
    db: Session,
    workspace_id: int,
    repo: str,
    call: Callable,
    deadline: float,
) -> int:
    """Walk the repository folders and save the list of .py files."""

    owner, name = repo.split("/", 1)

    stack = [""]
    found: dict[str, tuple[str, int]] = {}
    dirs = 0

    while stack:
        if time.monotonic() > deadline:
            raise RuntimeError("Scanning took too long. Press Index code again.")

        path = stack.pop()
        dirs += 1

        if dirs > MAX_DIRS:
            raise RuntimeError("Repository has too many folders for the code index.")

        entries = list_dir(call, owner, name, path)

        if path == "" and not entries:
            raise RuntimeError("Could not list the repository root.")

        for entry in entries:
            entry_path = entry.get("path")
            kind = entry.get("type")

            if not isinstance(entry_path, str):
                continue

            if kind == "dir":
                if not _skip_dir(entry_path):
                    stack.append(entry_path)

            elif kind == "file" and _wanted_file(entry_path, entry.get("size")):
                found[entry_path] = (
                    str(entry.get("sha") or ""),
                    int(entry.get("size") or 0),
                )

        if len(found) > MAX_FILES:
            raise RuntimeError("Repository has too many files for the code index.")

    existing = {
        f.path: f
        for f in db.query(CodeFile)
        .filter(CodeFile.workspace_id == workspace_id, CodeFile.repo == repo)
        .all()
    }

    for path, (sha, size) in found.items():
        row = existing.get(path)

        if row is None:
            db.add(
                CodeFile(
                    workspace_id=workspace_id, repo=repo, path=path,
                    sha=sha, size=size, attempts=0,
                )
            )
        elif row.sha != sha or row.size != size:
            row.sha = sha
            row.size = size
            row.attempts = 0

    for path, row in existing.items():
        if path not in found:
            db.query(CodeSymbol).filter(CodeSymbol.file_id == row.id).delete()
            db.delete(row)

    db.commit()

    return len(found)


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
    base = (CodeFile.workspace_id == workspace_id, CodeFile.repo == repo)

    files = db.query(func.count(CodeFile.id)).filter(*base).scalar() or 0
    indexed = (
        db.query(func.count(CodeFile.id))
        .filter(*base, CodeFile.indexed_sha == CodeFile.sha)
        .scalar()
        or 0
    )
    pending = (
        db.query(func.count(CodeFile.id))
        .filter(*base, _pending_filter())
        .scalar()
        or 0
    )
    symbols = (
        db.query(func.count(CodeSymbol.id))
        .filter(CodeSymbol.workspace_id == workspace_id, CodeSymbol.repo == repo)
        .scalar()
        or 0
    )
    last = db.query(func.max(CodeFile.indexed_at)).filter(*base).scalar()

    return {
        "repo": repo,
        "files": files,
        "indexed": indexed,
        "pending": pending,
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
) -> dict:
    """Scan (when asked or when nothing is saved yet), then index pending files."""

    if not dev.is_valid_repo(repo):
        raise ValueError("Repository must look like owner/repo.")

    deadline = time.monotonic() + budget_seconds
    owner, name = repo.split("/", 1)

    has_files = (
        db.query(func.count(CodeFile.id))
        .filter(CodeFile.workspace_id == workspace_id, CodeFile.repo == repo)
        .scalar()
        or 0
    )

    if scan or not has_files:
        scan_repo(db, workspace_id, repo, call, deadline)

    pending_rows = (
        db.query(CodeFile)
        .filter(
            CodeFile.workspace_id == workspace_id,
            CodeFile.repo == repo,
            _pending_filter(),
        )
        .order_by(CodeFile.path)
        .limit(300)
        .all()
    )

    processed = 0
    errors = 0

    for row in pending_rows:
        if time.monotonic() >= deadline - SAFETY_MARGIN:
            break

        row_id, path = row.id, row.path

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
        "processed": processed,
        "errors": errors,
        "done": status["files"] > 0 and status["pending"] == 0,
    }


def delete_repo_index(db: Session, workspace_id: int, repo: str) -> None:
    db.query(CodeSymbol).filter(
        CodeSymbol.workspace_id == workspace_id, CodeSymbol.repo == repo
    ).delete()
    db.query(CodeFile).filter(
        CodeFile.workspace_id == workspace_id, CodeFile.repo == repo
    ).delete()
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
        .filter(CodeFile.workspace_id == workspace_id)
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
