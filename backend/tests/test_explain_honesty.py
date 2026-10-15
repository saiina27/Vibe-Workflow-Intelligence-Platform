from types import SimpleNamespace

from app.ai.prompt_builder import build_prompt


def prompt_for(text):
    return build_prompt(
        memories=[], conversation_summary=None,
        history=[SimpleNamespace(role="user", content=text)],
        knowledge_chunks=[], include_memories=False,
        include_knowledge=False,
    )


def test_explain_prompt_does_not_force_a_how_it_works_description():
    prompt = prompt_for("explain how the provider cooldown works")

    assert "Not checked: I have not read your code" in prompt
    assert "What it is, Why it is this way, How it works" in prompt


def test_repo_code_question_gets_the_code_search_rule():
    prompt = prompt_for("how does the router work in my repo X")

    assert "does not mean the code is missing" in prompt
    assert "directory path returns its files" in prompt


def test_greeting_has_neither_rule():
    prompt = prompt_for("hi")

    assert "Not checked: I have not read your code" not in prompt
    assert "does not mean the code is missing" not in prompt
