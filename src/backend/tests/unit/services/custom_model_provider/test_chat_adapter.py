import json

import httpx
from langchain_core.messages import AIMessageChunk
from langflow.services.custom_model_provider.chat_adapter import OpenAICompatibleReasoningChatModel
from lfx.custom.custom_component.component import _apply_reasoning_chunk
from lfx.schema.content_types import ReasoningContent, ToolContent
from lfx.schema.message import Message


def _json_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload, headers={"content-type": "application/json"})


def test_non_streaming_raw_reasoning_survives_history_reload_and_tool_continuation():
    reasoning_details = [
        {"type": "reasoning.text", "text": "inspect inputs", "signature": "sig-123"},
        {"type": "reasoning.encrypted", "encrypted_content": "opaque"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        return _json_response(
            {
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 1,
                "model": "qwen3",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "reasoning_details": reasoning_details,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {"name": "lookup", "arguments": '{"city":"Paris"}'},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            }
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    model = OpenAICompatibleReasoningChatModel(
        model="qwen3",
        api_key="secret",
        base_url="https://gateway.example/v1",
        http_client=client,
    )
    response = model.invoke("weather?")
    assert response.additional_kwargs["reasoning_provider_data"] == {"reasoning_details": reasoning_details}

    persisted = Message.from_lc_message(response).model_dump_json()
    restored = Message.model_validate_json(persisted)
    reasoning = next(block for block in restored.content_blocks if isinstance(block, ReasoningContent))
    tool = next(block for block in restored.content_blocks if isinstance(block, ToolContent))
    assert reasoning.text == "inspect inputs"
    assert reasoning.provider_data == {"reasoning_details": reasoning_details}
    assert tool.id == "call-1"

    replay = model._get_request_payload([restored.to_lc_message()])
    assistant = replay["messages"][0]
    assert assistant["reasoning_details"] == reasoning_details
    assert assistant["tool_calls"][0]["id"] == "call-1"


def test_streaming_raw_reasoning_delta_is_preserved_separately_from_answer():
    chunks = [
        {"role": "assistant", "reasoning_content": "step "},
        {"reasoning_content": "one"},
        {"content": "answer"},
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        frames = [
            (
                "data: "
                + json.dumps(
                    {
                        "id": "chatcmpl-stream",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "qwen3",
                        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                    }
                )
                + "\n\n"
            )
            for delta in chunks
        ]
        frames.append("data: [DONE]\n\n")
        return httpx.Response(200, text="".join(frames), headers={"content-type": "text/event-stream"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    model = OpenAICompatibleReasoningChatModel(
        model="qwen3",
        api_key="secret",
        base_url="https://gateway.example/v1",
        http_client=client,
        streaming=True,
    )
    received = list(model.stream("hello"))
    reasoning = "".join(chunk.additional_kwargs.get("reasoning_content", "") for chunk in received)
    answer = "".join(chunk.content for chunk in received if isinstance(chunk.content, str))
    assert reasoning == "step one"
    assert answer == "answer"


def test_direct_model_stream_accumulates_reasoning_without_answer_contamination():
    message = Message(text="", sender="Machine", sender_name="AI", session_id="session")
    first = AIMessageChunk(
        content="",
        additional_kwargs={
            "reasoning_content": "step ",
            "reasoning_provider_data": {"reasoning_content": "step "},
        },
    )
    second = AIMessageChunk(
        content="",
        additional_kwargs={
            "reasoning_content": "one",
            "reasoning_provider_data": {"reasoning_content": "one"},
        },
    )
    answer = AIMessageChunk(content="answer")

    assert _apply_reasoning_chunk(message, first) is True
    assert _apply_reasoning_chunk(message, second) is True
    assert _apply_reasoning_chunk(message, answer) is False
    reasoning = next(block for block in message.content_blocks if isinstance(block, ReasoningContent))
    assert reasoning.text == "step one"
    assert reasoning.provider_data == {"reasoning_content": "step one"}
    assert message.text == ""
