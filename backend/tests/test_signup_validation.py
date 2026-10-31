import importlib
import pkgutil
from types import SimpleNamespace

import pytest

import app.models

for _m in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_m.name}")

from app.schemas.user import UserCreate
from app.services import auth_service, user_service


def make(**changes):
    data = dict(
        full_name="Saina Yadav",
        email="a@example.com",
        password="Passw0rd!123",
    )
    data.update(changes)

    return UserCreate(**data)


@pytest.fixture
def saved(monkeypatch):
    store = {}

    monkeypatch.setattr(
        user_service.user_repository, "get_user_by_email", lambda db, email: None
    )
    monkeypatch.setattr(
        user_service.user_repository,
        "create_user",
        lambda db, user: store.setdefault("user", user),
    )
    monkeypatch.setattr(user_service, "hash_password", lambda p: "hashed")

    return store


def test_valid_signup_creates_the_user_with_a_cleaned_name(saved):
    user = user_service.create_user(None, make(full_name="  Saina Yadav  "))

    assert user.full_name == "Saina Yadav"
    assert user.hashed_password == "hashed"


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"password": "short"}, "at least 8 characters"),
        ({"password": ""}, "at least 8 characters"),
        ({"password": "a" * 73}, "at most 72 bytes"),
        ({"password": "é" * 40}, "at most 72 bytes"),
        ({"full_name": "   "}, "Name cannot be empty"),
        ({"full_name": "x" * 101}, "at most 100 characters"),
    ],
)
def test_bad_signup_input_is_rejected_before_anything_is_saved(saved, changes, message):
    with pytest.raises(ValueError, match=message):
        user_service.create_user(None, make(**changes))

    assert "user" not in saved


def test_boundary_lengths_are_accepted(saved):
    user_service.create_user(None, make(password="a" * 72, full_name="x" * 100))

    assert saved["user"] is not None


# ---------------- login ----------------

class FakeQuery:
    def __init__(self, user):
        self.user = user

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.user


class FakeDb:
    def __init__(self, user=None):
        self.user = user

    def query(self, *args, **kwargs):
        return FakeQuery(self.user)


def test_unknown_email_still_runs_one_password_check(monkeypatch):
    calls = []
    monkeypatch.setattr(
        auth_service, "verify_password", lambda p, h: calls.append((p, h)) or False
    )

    assert auth_service.authenticate_user(FakeDb(None), "a@example.com", "pw") is None
    assert len(calls) == 1


def test_correct_password_returns_a_token(monkeypatch):
    user = SimpleNamespace(id=5, email="a@example.com", hashed_password="h")

    monkeypatch.setattr(auth_service, "verify_password", lambda p, h: True)
    monkeypatch.setattr(
        auth_service, "create_access_token", lambda data: f"token-{data['sub']}"
    )

    assert auth_service.authenticate_user(FakeDb(user), "a@example.com", "pw") == "token-5"


def test_wrong_password_returns_none(monkeypatch):
    user = SimpleNamespace(id=5, email="a@example.com", hashed_password="h")
    monkeypatch.setattr(auth_service, "verify_password", lambda p, h: False)

    assert auth_service.authenticate_user(FakeDb(user), "a@example.com", "pw") is None


def test_a_failing_password_check_means_invalid_not_a_crash(monkeypatch):
    user = SimpleNamespace(id=5, email="a@example.com", hashed_password="h")

    def broken(password, hashed):
        raise ValueError("password too long")

    monkeypatch.setattr(auth_service, "verify_password", broken)

    assert auth_service.authenticate_user(FakeDb(user), "a@example.com", "x" * 200) is None
