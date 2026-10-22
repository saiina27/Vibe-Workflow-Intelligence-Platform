import importlib
import json
import pkgutil
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models

for _m in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_m.name}")

from app.ai.prompt_builder import build_prompt
from app.ai.tools.code_search_tool import CodeSearchTool
from app.ai.tools.context import ToolContext
from app.ai.tools.registry import MAX_EXPOSED_TOOLS, ToolRegistry
from app.db.base import Base
from app.models.code_file import CodeFile, CodeSymbol
from app.services import code_index_service as cidx
from app.services import dev_events_service as dev

REPO = "o/r"

SAMPLE = '''"""module"""
import time

MAX_TOOLS = 12

class ProviderRouter:
    """Routes AI requests."""

    def _in_cooldown(self, provider_name):
        """Is the provider skipped?"""
        return False

    async def stream(self):
        pass

@router.post("/dev-events/sync")
async def sync_dev_events():
    """Sync events."""
'''


# ---------------- fake GitHub results ----------------

class TextBlock(BaseModel):
    text: str
    type: str = "text"


class Inner(BaseModel):
    uri: str
    text: str


class ResBlock(BaseModel):
    resource: Inner
    type: str = "resource"


class FakeResult(BaseModel):
    content: list[TextBlock | ResBlock]
    is_error: bool = False


def dir_result(entries):
    return FakeResult(content=[TextBlock(text=json.dumps(entries))])


def file_result(text):
    return FakeResult(
        content=[
            TextBlock(text="successfully downloaded text file (SHA: x)"),
            ResBlock(resource=Inner(uri="repo://x", text=text)),
        ]
    )


def entry(kind, path, sha="s1", size=100):
    return {"type": kind, "path": path, "name": path.split("/")[-1],
            "sha": sha, "size": size}


def make_tree(router_sha="r1"):
    return {
        "": [
            entry("dir", "backend"), entry("dir", "node_modules"),
            entry("dir", ".github"), entry("file", "README.md", size=50),
        ],
        "backend": [
            entry("dir", "backend/app"),
            entry("file", "backend/main.py", "m1", 200),
            entry("file", "backend/big.py", "b1", 999_999),
        ],
        "backend/app": [
            entry("file", "backend/app/router.py", router_sha, 400),
            entry("file", "backend/app/__init__.py", "e1", 0),
            entry("dir", "backend/app/__pycache__"),
            entry("file", "backend/app/data.json", "j1", 10),
        ],
    }


FILES = {
    "backend/main.py": "APP_NAME = 'x'\n",
    "backend/app/router.py": SAMPLE,
}


class FakeGitHub:
    def __init__(self, tree=None, files=None, root_needs_empty_path=False):
        self.tree = tree or make_tree()
        self.files = FILES if files is None else files
        self.root_needs_empty_path = root_needs_empty_path
        self.calls = []

    def __call__(self, tool, args):
        assert tool == "get_file_contents"
        path = args["path"]
        self.calls.append(path)

        if path in self.files:
            return file_result(self.files[path])

        if path == "/":
            return dir_result([] if self.root_needs_empty_path else self.tree[""])

        if path == "":
            return dir_result(self.tree[""])

        return dir_result(self.tree.get(path, []))

    def fetched_files(self):
        return [p for p in self.calls if p.endswith(".py")]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[CodeFile.__table__, CodeSymbol.__table__]
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# ---------------- parser ----------------

def by_qualname(symbols):
    return {s["qualname"]: s for s in symbols}


def test_parser_finds_classes_methods_functions_constants():
    found = by_qualname(cidx.parse_symbols(SAMPLE))

    assert found["MAX_TOOLS"]["kind"] == "constant"
    assert found["ProviderRouter"]["kind"] == "class"
    assert found["ProviderRouter"]["doc"] == "Routes AI requests."
    assert found["ProviderRouter._in_cooldown"]["kind"] == "method"
    assert found["ProviderRouter._in_cooldown"]["doc"] == "Is the provider skipped?"
    assert found["ProviderRouter.stream"]["kind"] == "method"
    assert found["sync_dev_events"]["kind"] == "function"
    assert found["sync_dev_events"]["doc"] == "POST /dev-events/sync · Sync events."
    assert all(s["line"] > 0 for s in found.values())


def test_parser_falls_back_to_regex_on_syntax_errors():
    broken = "class Ok:\n    def method(self):\n        pass\n\ndef bad(:\n"
    found = by_qualname(cidx.parse_symbols(broken))

    assert found["Ok"]["kind"] == "class"
    assert found["method"]["kind"] == "method"
    assert found["bad"]["kind"] == "function"


def test_parser_caps_symbols_per_file():
    source = "\n".join(f"def f{i}():\n    pass" for i in range(500))
    assert len(cidx.parse_symbols(source)) == cidx.MAX_SYMBOLS_PER_FILE


def test_parser_stores_names_not_code():
    for symbol in cidx.parse_symbols(SAMPLE):
        assert "return False" not in json.dumps(symbol)


# ---------------- reading results ----------------

def test_file_text_reads_the_resource_block():
    assert cidx.file_text(file_result("print(1)")) == "print(1)"
    assert cidx.file_text(dir_result([])) is None


def test_file_text_raises_on_tool_error():
    bad = FakeResult(content=[TextBlock(text="x")], is_error=True)

    with pytest.raises(RuntimeError):
        cidx.file_text(bad)


# ---------------- scan and index ----------------

def tree_with_noise():
    tree = make_tree()
    tree[""] = tree[""] + [entry("dir", "frontend"), entry("dir", "docs")]
    return tree


def run_until_done(db, gh, rounds=12, **kwargs):
    out = None

    for _ in range(rounds):
        out = cidx.run_batch(db, 1, REPO, gh, budget_seconds=30, **kwargs)

        if out["done"]:
            break

    return out


def test_first_run_scans_and_indexes_only_wanted_files(db):
    gh = FakeGitHub(tree=tree_with_noise())
    out = cidx.run_batch(db, 1, REPO, gh, budget_seconds=30)

    assert out["files"] == 2
    assert out["indexed"] == 2
    assert out["pending"] == 0 and out["dirs_left"] == 0
    assert out["done"] is True
    assert out["symbols"] > 0

    paths = {
        f.path for f in db.query(CodeFile).filter(CodeFile.size >= 0).all()
    }
    assert paths == {"backend/main.py", "backend/app/router.py"}

    assert {"/", "backend", "backend/app"} <= set(gh.calls)

    for skipped in ("node_modules", ".github", "__pycache__", "frontend", "docs"):
        assert not any(skipped in c for c in gh.calls)


def test_scan_is_resumable_and_keeps_its_progress(db):
    gh = FakeGitHub()
    first = cidx.run_batch(db, 1, REPO, gh, budget_seconds=30, max_calls=2)

    assert first["scanned"] == 2
    assert first["dirs_left"] == 1
    assert first["done"] is False and first["processed"] == 0

    saved_dirs = db.query(CodeFile).filter(CodeFile.size == cidx.DIR_SIZE).count()
    assert saved_dirs == 3  # root, backend and backend/app are remembered

    out = run_until_done(db, gh, max_calls=2)

    assert out["done"] is True
    assert out["files"] == 2 and out["indexed"] == 2

    # backend/app was listed once only: nothing was re-scanned from zero
    assert gh.calls.count("backend") == 1
    assert gh.calls.count("backend/app") == 1


def test_status_counts_files_not_folders(db):
    out = run_until_done(db, FakeGitHub())

    assert out["files"] == 2
    assert cidx.index_status(db, 1, REPO)["files"] == 2
    assert cidx.workspace_index_counts(db, 1)["files"] == 2
    assert db.query(CodeFile).filter(CodeFile.size == cidx.DIR_SIZE).count() == 3


def test_second_run_fetches_nothing_and_changed_files_are_refetched(db):
    cidx.run_batch(db, 1, REPO, FakeGitHub(), budget_seconds=30)

    again = FakeGitHub()
    out = cidx.run_batch(db, 1, REPO, again, scan=False, budget_seconds=30)
    assert again.calls == [] and out["done"] is True

    changed = FakeGitHub(tree=make_tree(router_sha="r2"))
    out = run_until_done(db, changed, scan=True)

    assert changed.fetched_files() == ["backend/app/router.py"]
    assert out["done"] is True


def test_deleted_files_are_removed_with_their_symbols(db):
    cidx.run_batch(db, 1, REPO, FakeGitHub(), budget_seconds=30)

    tree = make_tree()
    tree["backend"] = [entry("dir", "backend/app")]
    run_until_done(db, FakeGitHub(tree=tree), scan=True)

    left = {f.path for f in db.query(CodeFile).filter(CodeFile.size >= 0).all()}
    assert left == {"backend/app/router.py"}
    assert all(s.path == "backend/app/router.py" for s in db.query(CodeSymbol).all())


def test_removed_folder_disappears_with_everything_under_it(db):
    cidx.run_batch(db, 1, REPO, FakeGitHub(), budget_seconds=30)

    tree = make_tree()
    tree["backend"] = [entry("file", "backend/main.py", "m1", 200)]
    run_until_done(db, FakeGitHub(tree=tree), scan=True)

    paths = {f.path for f in db.query(CodeFile).all()}
    assert not any(p.startswith("backend/app") for p in paths)
    assert all(s.path == "backend/main.py" for s in db.query(CodeSymbol).all())


def test_root_listing_falls_back_to_empty_path(db):
    gh = FakeGitHub(root_needs_empty_path=True)
    out = run_until_done(db, gh)

    assert out["files"] == 2
    assert gh.calls[:2] == ["/", ""]


def test_failing_file_is_given_up_after_three_attempts(db):
    files = {"backend/app/router.py": SAMPLE}  # main.py cannot be read

    for _ in range(3):
        out = cidx.run_batch(db, 1, REPO, FakeGitHub(files=files), budget_seconds=30)

    assert out["pending"] == 0 and out["done"] is True
    failed = db.query(CodeFile).filter_by(path="backend/main.py").one()
    assert failed.attempts == 3 and failed.error


def test_zero_budget_does_no_github_calls_and_is_not_done(db):
    gh = FakeGitHub()
    out = cidx.run_batch(db, 1, REPO, gh, budget_seconds=0)

    assert gh.calls == []
    assert out["scanned"] == 0 and out["processed"] == 0
    assert out["done"] is False and out["dirs_left"] == 1


def test_sync_allowlist_has_file_reads_but_no_write_tools():
    assert "get_file_contents" in dev.ALLOWED_SYNC_TOOLS
    assert not any(
        n.startswith(("create_", "push_", "merge_", "delete_", "update_"))
        for n in dev.ALLOWED_SYNC_TOOLS
    )


# ---------------- search ----------------

def add(db, ws, path, qual, kind="method", doc=None, repo=REPO):
    db.add(CodeSymbol(
        file_id=1, workspace_id=ws, repo=repo, path=path,
        name=qual.split(".")[-1], qualname=qual, kind=kind, line=10, doc=doc,
    ))


@pytest.fixture
def indexed(db):
    add(db, 1, "backend/app/ai/router.py", "ProviderRouter._in_cooldown")
    add(db, 1, "backend/app/ai/router.py", "ProviderRouter._record_failure",
        doc="After a quota error skip that provider for a while")
    add(db, 1, "backend/app/ai/providers/registry.py", "ProviderRegistry", "class")
    add(db, 1, "tests/test_smart_routing.py", "test_cooldown_expires", "function")
    add(db, 1, "backend/app/core/config.py", "GROQ_MODEL", "constant")
    add(db, 2, "backend/app/ai/router.py", "OtherWorkspace._in_cooldown")
    db.commit()
    return db


def test_search_ranks_the_real_match_first_and_tests_lower(indexed):
    rows = cidx.search_symbols(indexed, 1, ["provider cooldown"])

    assert rows[0].qualname == "ProviderRouter._in_cooldown"
    assert rows[-1].path.startswith("tests/") or all(
        r.path != "tests/test_smart_routing.py" for r in rows[:2]
    )


def test_search_is_workspace_scoped_and_handles_wildcards(indexed):
    rows = cidx.search_symbols(indexed, 1, ["cooldown"])
    assert all(r.workspace_id == 1 for r in rows)

    assert cidx.search_symbols(indexed, 1, ["%"]) == []
    assert cidx.search_symbols(indexed, 1, ["_"]) == []
    assert cidx.search_symbols(indexed, 1, []) == []


def test_search_matches_docstrings_and_repo_filter(indexed):
    rows = cidx.search_symbols(indexed, 1, ["quota"])
    assert [r.qualname for r in rows] == ["ProviderRouter._record_failure"]

    assert cidx.search_symbols(indexed, 1, ["cooldown"], repo="nope") == []


# ---------------- tool ----------------

def make_tool(db, ws=1):
    return CodeSearchTool(ToolContext(db=db, workspace_id=ws, user_id=1))


def test_tool_returns_path_line_symbol(indexed):
    indexed.add(CodeFile(workspace_id=1, repo=REPO, path="backend/app/ai/router.py",
                         sha="a", indexed_sha="a"))
    indexed.commit()

    out = make_tool(indexed).execute(keywords=["cooldown"], query=None, repo=None)

    assert out["success"] is True and out["count"] >= 1
    first = out["matches"][0]
    assert set(first) == {"repo", "path", "line", "symbol", "kind", "doc"}
    assert "note" not in out


def test_tool_explains_an_empty_or_partial_index(db):
    assert "Index code" in make_tool(db).execute(keywords=["cooldown"])["note"]

    add(db, 1, "a.py", "Thing")
    db.add(CodeFile(workspace_id=1, repo=REPO, path="a.py", sha="a", indexed_sha="a"))
    db.add(CodeFile(workspace_id=1, repo=REPO, path="b.py", sha="b"))
    db.commit()

    assert "partial" in make_tool(db).execute(keywords=["thing"])["note"]


def test_tool_rejects_empty_input_and_accepts_null_args(db):
    assert make_tool(db).execute()["success"] is False
    assert make_tool(db).execute(keywords=None, query="thing", repo=None)["success"] is True


def test_tool_schema_is_nullable_and_nothing_is_required(db):
    params = make_tool(db).parameters

    assert params["required"] == []
    assert all("null" in p["type"] for p in params["properties"].values())


# ---------------- registry and prompt ----------------

class FakeTool:
    def __init__(self, name, plugin=None):
        self.name = name
        self.description = f"{name} tool"
        self.parameters = {"type": "object", "properties": {}}
        self.plugin_name = plugin


def prompt_for(text, tracked=None):
    return build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False, tracked_repos=tracked,
    )


def test_code_questions_expose_find_in_code_and_no_write_tools():
    reg = ToolRegistry()
    for n in ("get_me", "search_code", "get_file_contents", "search_repositories",
              "list_commits", "create_pull_request", "push_files"):
        reg.register(FakeTool(n, "github"))
    for n in ("search_web", "search_knowledge", "search_memory", "find_in_code"):
        reg.register(FakeTool(n))

    text = "explain how the provider cooldown works"
    names = {d.name for d in reg.definitions_for_prompt(prompt_for(text, [REPO]))}

    assert {"find_in_code", "get_file_contents"} <= names
    assert "list_commits" not in names
    assert not (names & {"create_pull_request", "push_files"})
    assert len(names) <= MAX_EXPOSED_TOOLS


def test_prompt_tells_the_model_to_use_the_index_first():
    prompt = prompt_for("explain how the provider cooldown works", [REPO])

    assert "first call find_in_code" in prompt
    assert "then read that file with get_file_contents" in prompt
