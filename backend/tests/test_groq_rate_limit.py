import pytest

from app.ai.providers.groq import GroqProvider


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Please try again in 112.499999ms.", 0.1125),
        ("Please try again in 1.4025s.", 1.4025),
        ("Please try again in 1m17.328s.", 77.328),
        ("no wait hint here", None),
    ],
)
def test_retry_after_seconds(message, expected):
    got = GroqProvider._retry_after_seconds(message)

    if expected is None:
        assert got is None
    else:
        assert got == pytest.approx(expected, rel=1e-3)
