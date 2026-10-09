from types import SimpleNamespace

import pytest
from lfx.base.models.reasoning_normalization import ReasoningStreamNormalizer, normalize_reasoning_content


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reasoning_details", [{"type": "reasoning", "text": "details"}]),
        ("reasoning_content", "reasoning content"),
        ("reasoning", "reasoning"),
        ("thinking", "thinking"),
        ("reasoning_text", "reasoning text"),
        ("thinking_content", "thinking content"),
        ("thought", "thought"),
        ("thoughts", "thoughts"),
    ],
)
def test_normalizes_supported_reasoning_fields(field, value):
    events = normalize_reasoning_content({"content": "answer", field: value})
    assert [event.kind for event in events] == ["reasoning", "answer"]
    assert events[0].text
    assert events[1].text == "answer"


def test_structured_blocks_take_precedence_over_fields_and_tags():
    payload = {
        "content": [
            {"type": "reasoning", "text": "structured"},
            {"type": "text", "text": "answer <think>ordinary</think>"},
        ],
        "reasoning_content": "lower priority",
    }
    events = normalize_reasoning_content(payload)
    assert [(event.kind, event.text) for event in events] == [
        ("reasoning", "structured"),
        ("answer", "answer <think>ordinary</think>"),
    ]


def test_tag_fallback_is_conservative_and_preserves_incomplete_or_inline_tags():
    inline = normalize_reasoning_content({"content": "Explain the <think> tag in prose."})
    incomplete = normalize_reasoning_content({"content": "<think>unfinished"})
    assert [(event.kind, event.text) for event in inline] == [("answer", "Explain the <think> tag in prose.")]
    assert [(event.kind, event.text) for event in incomplete] == [("answer", "<think>unfinished")]


def test_streaming_tag_parser_handles_every_chunk_boundary():
    source = "<thinking>step one</thinking>final"
    for split in range(1, len(source)):
        normalizer = ReasoningStreamNormalizer()
        normalizer.feed(SimpleNamespace(content=source[:split]))
        normalizer.feed(SimpleNamespace(content=source[split:]))
        assert [(event.kind, event.text) for event in normalizer.finalize()] == [
            ("reasoning", "step one"),
            ("answer", "final"),
        ]


def test_streaming_field_precedence_and_tool_capture():
    normalizer = ReasoningStreamNormalizer()
    normalizer.feed({"content": "an", "reasoning": "low", "tool_call_chunks": [{"id": "call-1"}]})
    normalizer.feed({"content": "swer", "reasoning_content": "high"})
    events = normalizer.finalize()
    assert [(event.kind, event.text) for event in events[:2]] == [
        ("reasoning", "high"),
        ("answer", "answer"),
    ]
    assert events[2].kind == "tool"


def test_stream_and_final_reconciliation_deduplicates_reasoning_and_answer():
    normalizer = ReasoningStreamNormalizer()
    normalizer.feed({"reasoning_content": "step ", "content": "an"})
    normalizer.feed({"reasoning_content": "one", "content": "swer"})
    events = normalizer.reconcile_final({"reasoning_content": "step one", "content": "answer"})
    assert [(event.kind, event.text) for event in events] == [
        ("reasoning", "step one"),
        ("answer", "answer"),
    ]


def test_reasoning_controls_and_token_counts_are_not_display_text():
    events = normalize_reasoning_content(
        {
            "content": "answer",
            "reasoning_effort": "high",
            "reasoning_tokens": 128,
            "budget_tokens": 256,
        }
    )
    assert [(event.kind, event.text) for event in events] == [("answer", "answer")]
