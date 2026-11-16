from types import SimpleNamespace

import pytest

from app.ai.prompt_builder import build_prompt


def prompt_for(text):
    return build_prompt(
        [], None, [SimpleNamespace(role="user", content=text)], [], False, False
    )


@pytest.mark.parametrize(
    "text",
    [
        "show the latest commits of my repo X",
        "what happened on 6 Oct",
        "explain how the provider cooldown works",
        "hi",
        "summarize my uploaded PDF",
    ],
)
def test_questions_without_slack_do_not_carry_the_slack_answer_rules(text):
    assert "SLACK ANSWERS" not in prompt_for(text)


@pytest.mark.parametrize(
    "text",
    [
        "what did the team say about deployment on Slack",
        "search Slack for deployment",
        "any update from the team on the release",
    ],
)
def test_slack_and_decision_questions_keep_them(text):
    assert "SLACK ANSWERS" in prompt_for(text)


def test_input_that_cannot_be_classified_keeps_them():
    assert "SLACK ANSWERS" in prompt_for("यह क्या है")


def test_the_other_tool_rules_stay_for_a_github_question():
    prompt = prompt_for("show the latest commits of my repo X")

    assert "TOOL CHOICE RULES" in prompt
    assert "- Only use tools in your tool list." in prompt
    assert "search_history covers all tracked repositories" in prompt


def test_the_block_is_what_is_saved():
    github = len(prompt_for("show the latest commits of my repo X"))
    slack = len(prompt_for("what did the team say about deployment on Slack"))

    assert slack - github > 500


def test_decision_questions_use_the_decision_section_not_the_slack_answer_block():
    prompt = prompt_for("why did we choose Groq as the fallback provider")

    assert "DECISION QUESTIONS AND EXPLAIN MODE" in prompt
    assert "slack_search_public" in prompt
    assert "SLACK ANSWERS" not in prompt
