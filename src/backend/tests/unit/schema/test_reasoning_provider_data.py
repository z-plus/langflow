import pytest
from langflow.schema.content_types import MAX_REASONING_PROVIDER_DATA_BYTES, ReasoningContent
from langflow.schema.message import Message
from langflow.services.database.models.message.model import MessageTable
from lfx.schema.content_types import ReasoningContent as LfxReasoningContent


def test_reasoning_provider_data_round_trips_through_json_and_message_table():
    provider_data = {
        "type": "reasoning.encrypted",
        "signature": "sig-123",
        "encrypted_content": "opaque-payload",
        "details": [{"type": "reasoning.text", "text": "step"}],
    }
    reasoning = ReasoningContent(text="visible reasoning", provider_data=provider_data)
    restored = ReasoningContent.model_validate_json(reasoning.model_dump_json())
    assert restored.provider_data == provider_data

    message = Message(
        text="answer",
        sender="Machine",
        sender_name="AI",
        session_id="session",
        content_blocks=[LfxReasoningContent(text="visible reasoning", provider_data=provider_data)],
    )
    table = MessageTable.from_message(message)
    persisted = table.content_blocks[0]
    assert persisted["text"] == "visible reasoning"
    assert persisted["provider_data"] == provider_data


def test_reasoning_provider_data_is_optional_for_legacy_messages():
    reasoning = ReasoningContent.model_validate({"type": "reasoning", "text": "legacy"})
    assert reasoning.provider_data is None


def test_reasoning_provider_data_rejects_non_json_and_oversized_values():
    with pytest.raises(ValueError, match="JSON-compatible"):
        ReasoningContent(text="visible", provider_data={"bad": object()})
    with pytest.raises(ValueError, match="provider_data exceeds"):
        ReasoningContent(text="visible", provider_data={"opaque": "x" * MAX_REASONING_PROVIDER_DATA_BYTES})
