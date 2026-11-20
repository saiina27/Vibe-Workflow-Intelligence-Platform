from types import SimpleNamespace

from app.ai.prompt_builder import build_prompt

CATEGORIES = [
    "Code & Project Understanding", "Technical Guidance", "Knowledge & Documents",
    "Memory", "Web Search", "GitHub Integration", "Slack Integration",
    "Developer History & Digest", "Tool-Based Workflows", "Persistent Conversations",
]


def prompt_for(text):
    return build_prompt(
        [], None, [SimpleNamespace(role="user", content=text)], [], False, False
    )


def test_the_overview_lists_all_ten_categories_and_the_v1_features():
    prompt = prompt_for("what can you do?")

    for name in CATEGORIES:
        assert name in prompt, name

    for text in ("weekly digest", "decisions with the reason", "suggestions only",
                 "watch words", "Vibe never posts to Slack"):
        assert text in prompt, text

    assert "componentswork" not in prompt and "architectureand" not in prompt


def test_other_questions_do_not_get_the_overview():
    assert "Developer History & Digest" not in prompt_for("show the latest commits of my repo X")
