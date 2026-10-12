from types import SimpleNamespace

import pytest

from app.ai.gateway import REQUEST_TOO_LARGE_MESSAGE, AIGateway
from app.ai.prompt_builder import TOOL_RULE_WORDS, build_prompt
from app.ai.tools import registry as reg
from app.ai.tools.registry import ToolRegistry

CAP_TABLE = "### What I Can Help With"
GITHUB_RULE = "GITHUB REPOSITORY RULE"
TOOL_CHOICE = "TOOL CHOICE RULES"
DECISION = "DECISION QUESTIONS AND EXPLAIN MODE"


def prompt_for(text=None, turns=None):
    history = turns or [SimpleNamespace(role="user", content=text)]

    return build_prompt(
        memories=[],
        conversation_summary=None,
        history=history,
        knowledge_chunks=[],
        include_memories=False,
        include_knowledge=False,
    )


def turn(role, content):
    return SimpleNamespace(role=role, content=content)


def test_greeting_gets_the_minimal_prompt():
    prompt = prompt_for("hi")

    for gone in (CAP_TABLE, GITHUB_RULE, TOOL_CHOICE, DECISION):
        assert gone not in prompt

    for kept in (
        "MEMORY CONFIRMATION RULE",
        "KNOWLEDGE / DOCUMENT RULE",
        "IMPORTANT TOOL SELECTION RULES",
        "RESPONSE FORMAT RULES",
        "READ-ONLY",
        "ACCURACY",
        "CURRENT CONVERSATION",
        "RESPONSE INSTRUCTION",
        "Do not describe or list Vibe AI's capabilities",
    ):
        assert kept in prompt


@pytest.mark.parametrize(
    "text",
    [
        "summarize my uploaded PDF",
        "do you remember my name",
        "what is the latest Python version",
        "explain how the provider cooldown works",
    ],
)
def test_general_questions_skip_github_slack_and_capability_rules(text):
    prompt = prompt_for(text)

    assert GITHUB_RULE not in prompt
    assert TOOL_CHOICE not in prompt
    assert CAP_TABLE not in prompt


@pytest.mark.parametrize(
    "text",
    [
        "show open issues in my repo X",
        "what did the team say in Slack",
        "5 Oct ko humne kya changes kiye the",
        "pichhli chat mein kya hua tha",
        "was there ever a commit about rate limiting",
        "koi query aayi hai kya vibe ke baare mein",
        "any update on my vibe project",
    ],
)
def test_github_slack_history_and_chat_questions_keep_tool_rules(text):
    prompt = prompt_for(text)

    assert TOOL_CHOICE in prompt
    assert GITHUB_RULE in prompt
    assert CAP_TABLE not in prompt


@pytest.mark.parametrize(
    "text",
    [
        "what can you do",
        "introduce yourself",
        "tell me about yourself",
        "What is Vibe AI?",
    ],
)
def test_capability_questions_get_the_full_table(text):
    prompt = prompt_for(text)

    assert CAP_TABLE in prompt
    assert "Preserve all nine capability categories" in prompt


@pytest.mark.parametrize(
    "text",
    [
        "why did we choose Groq as the fallback provider",
        "explain how the router works",
        "samjhao ye kaise kaam karta hai",
    ],
)
def test_decision_and_explain_questions_get_that_section(text):
    assert DECISION in prompt_for(text)


def test_plain_github_question_has_no_decision_section():
    assert DECISION not in prompt_for("show the branches of my repo X")


def test_short_followup_uses_the_previous_question():
    prompt = prompt_for(
        turns=[
            turn("user", "any update on my vibe project"),
            turn("assistant", "Which repository?"),
            turn("user", "vibe"),
        ]
    )
    assert TOOL_CHOICE in prompt

    quiet = prompt_for(
        turns=[
            turn("user", "what is the latest Python version"),
            turn("assistant", "3.14"),
            turn("user", "thanks"),
        ]
    )
    assert TOOL_CHOICE not in quiet


def test_unclassifiable_input_sends_everything():
    for prompt in (prompt_for("यह क्या है"), prompt_for(turns=[turn("assistant", "x")])):
        for section in (CAP_TABLE, GITHUB_RULE, TOOL_CHOICE, DECISION):
            assert section in prompt


def test_full_prompt_keeps_the_original_section_order():
    prompt = prompt_for("what can you do? explain my repo commits")

    order = [
        "CAPABILITY OVERVIEW RULE",
        "KNOWLEDGE / DOCUMENT RULE",
        GITHUB_RULE,
        CAP_TABLE,
        TOOL_CHOICE,
        DECISION,
        "RESPONSE FORMAT RULES",
    ]
    positions = [prompt.index(name) for name in order]

    assert positions == sorted(positions)


def test_prompt_gate_words_cover_registry_intent_words():
    for group in (
        reg.SLACK_INTENT_WORDS,
        reg.CHAT_INTENT_WORDS,
        reg.HISTORY_INTENT_WORDS,
        reg.PAST_PERIOD_WORDS,
        reg.EXISTENCE_WORDS,
    ):
        assert group <= TOOL_RULE_WORDS


def test_prompt_size_budget():
    assert len(prompt_for("hi")) < 8000
    assert len(prompt_for("show the latest commits of my repo X")) < 12500
    assert len(prompt_for("what can you do? explain my repo commits")) > 13000


def test_registry_still_finds_the_latest_user_message_in_a_gated_prompt():
    assert ToolRegistry._latest_user_text(prompt_for("hi")) == "hi"
    assert (
        ToolRegistry._latest_user_text(prompt_for("show my repo commits"))
        == "show my repo commits"
    )


def test_request_too_large_gets_a_friendly_message():
    def boom():
        raise RuntimeError(
            "Error code: 413 - {'error': {'message': 'Request too large "
            "for model openai/gpt-oss-20b on tokens per minute'}}"
        )
        yield

    events = list(AIGateway._guard_unexposed_tool_errors(boom()))

    assert events[-1].text == REQUEST_TOO_LARGE_MESSAGE
