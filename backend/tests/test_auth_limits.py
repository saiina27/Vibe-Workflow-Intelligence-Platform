import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.routes import auth as auth_routes
from app.api.routes import users as users_routes
from app.core.auth_limits import SlidingWindow, wait_text
from app.dependencies import auth as auth_dep
from app.dependencies.database import get_db


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


# ---------------- the counter ----------------

def test_blocks_after_the_limit_and_frees_after_the_window():
    clock = Clock()
    window = SlidingWindow(3, 600, clock=clock)

    for _ in range(3):
        assert window.wait_seconds("ip") == 0
        window.hit("ip")
        clock.now += 1

    wait = window.wait_seconds("ip")
    assert 1 <= wait <= 600

    clock.now += 600
    assert window.wait_seconds("ip") == 0


def test_keys_are_independent_and_expired_keys_are_forgotten():
    clock = Clock()
    window = SlidingWindow(1, 60, clock=clock)

    window.hit("a")
    assert window.wait_seconds("a") > 0
    assert window.wait_seconds("b") == 0

    clock.now += 61
    assert window.wait_seconds("a") == 0
    assert "a" not in window._events


def test_limit_zero_is_off():
    window = SlidingWindow(0, 60)

    for _ in range(100):
        window.hit("a")

    assert window.wait_seconds("a") == 0


@pytest.mark.parametrize(
    "seconds, text",
    [(1, "1 second"), (45, "45 seconds"), (60, "1 minute"),
     (61, "2 minutes"), (600, "10 minutes")],
)
def test_wait_text(seconds, text):
    assert wait_text(seconds) == text


# ---------------- login and signup routes ----------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth_routes, "login_failures", SlidingWindow(3, 600))
    monkeypatch.setattr(users_routes, "signup_per_ip", SlidingWindow(2, 3600))
    monkeypatch.setattr(users_routes, "signup_global", SlidingWindow(100, 86400))

    app = FastAPI()
    app.include_router(auth_routes.router)
    app.include_router(users_routes.router)
    app.dependency_overrides[get_db] = lambda: None

    return TestClient(app)


def login(client, password="wrong"):
    return client.post(
        "/auth/login",
        data={"username": "a@example.com", "password": password},
    )


def test_wrong_passwords_are_blocked_after_the_limit(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "authenticate_user", lambda db, u, p: None)

    assert [login(client).status_code for _ in range(3)] == [401, 401, 401]

    blocked = login(client)
    assert blocked.status_code == 429
    assert "Too many failed login attempts" in blocked.json()["detail"]
    assert int(blocked.headers["retry-after"]) > 0


def test_successful_logins_are_never_counted(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "authenticate_user", lambda db, u, p: "token")

    assert all(login(client).status_code == 200 for _ in range(20))


def test_signups_are_limited_per_network(client, monkeypatch):
    def exists(db, data):
        raise ValueError("exists")

    monkeypatch.setattr(users_routes, "create_user", exists)

    body = {"full_name": "A B", "email": "a@example.com", "password": "Passw0rd!123"}
    first = client.post("/users/", json=body)
    second = client.post("/users/", json=body)
    third = client.post("/users/", json=body)

    assert (first.status_code, second.status_code) == (400, 400)
    assert third.status_code == 429
    assert "sign-ups" in third.json()["detail"].lower()


def test_global_signup_cap_pauses_everyone(client, monkeypatch):
    monkeypatch.setattr(users_routes, "signup_per_ip", SlidingWindow(100, 3600))
    monkeypatch.setattr(users_routes, "signup_global", SlidingWindow(2, 86400))
    monkeypatch.setattr(
        users_routes, "create_user", lambda db, data: (_ for _ in ()).throw(ValueError("x"))
    )

    body = {"full_name": "A B", "email": "a@example.com", "password": "Passw0rd!123"}
    codes = [client.post("/users/", json=body).status_code for _ in range(3)]

    assert codes == [400, 400, 429]


# ---------------- tokens ----------------

def test_token_with_a_non_numeric_subject_is_401_not_500(monkeypatch):
    monkeypatch.setattr(auth_dep, "verify_access_token", lambda token: {"sub": "abc"})

    with pytest.raises(HTTPException) as error:
        auth_dep.get_current_user(token="x", db=None)

    assert error.value.status_code == 401
