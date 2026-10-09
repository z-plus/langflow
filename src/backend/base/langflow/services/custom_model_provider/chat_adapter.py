from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

_REASONING_FIELDS = (
    "reasoning_details",
    "reasoning_content",
    "reasoning",
    "thinking",
    "reasoning_text",
    "thinking_content",
    "thought",
    "thoughts",
)
_REPLAY_KEY = "reasoning_provider_data"


def _as_dict(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(warnings=False)
        if isinstance(dumped, Mapping):
            return dumped
    return {}


def _reasoning_fields(value: Any) -> dict[str, Any]:
    data = _as_dict(value)
    return {field: data[field] for field in _REASONING_FIELDS if field in data and data[field] is not None}


def _attach_reasoning(message: Any, raw_message: Any) -> None:
    fields = _reasoning_fields(raw_message)
    if not fields:
        return
    message.additional_kwargs.update(fields)
    message.additional_kwargs[_REPLAY_KEY] = fields


class OpenAICompatibleReasoningChatModel(ChatOpenAI):
    """ChatOpenAI variant that preserves compatible reasoning fields for display and replay."""

    def _create_chat_result(self, response: Any, generation_info: dict | None = None):
        result = super()._create_chat_result(response, generation_info)
        response_data = _as_dict(response)
        for generation, choice in zip(result.generations, response_data.get("choices", []), strict=False):
            _attach_reasoning(generation.message, _as_dict(choice).get("message", {}))
        return result

    def _convert_chunk_to_generation_chunk(
        self, chunk: dict, default_chunk_class: type, base_generation_info: dict | None
    ):
        generation = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        if generation is None:
            return None
        choices = chunk.get("choices", []) or chunk.get("chunk", {}).get("choices", [])
        if choices:
            _attach_reasoning(generation.message, _as_dict(choices[0]).get("delta", {}))
        return generation

    def _get_request_payload(self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        source_messages = input_.to_messages() if hasattr(input_, "to_messages") else input_
        if not isinstance(source_messages, list):
            return payload
        for source, target in zip(source_messages, payload.get("messages", []), strict=False):
            if not isinstance(source, AIMessage) or target.get("role") != "assistant":
                continue
            replay = source.additional_kwargs.get(_REPLAY_KEY)
            if isinstance(replay, Mapping):
                target.update({field: replay[field] for field in _REASONING_FIELDS if field in replay})
        return payload
