from types import SimpleNamespace

from app.ai.prompt_builder import build_prompt


def test_prompt_has_readonly_and_truncation_rules():
    prompt = build_prompt(
        memories=[],
        conversation_summary=None,
        history=[SimpleNamespace(role="user", content="hi")],
        knowledge_chunks=[],
        include_memories=False,
        include_knowledge=False,
    )
    assert "READ-ONLY" in prompt
    assert "Never offer or promise" in prompt
    assert "Result shortened" in prompt
    assert "ACCURACY" in prompt
