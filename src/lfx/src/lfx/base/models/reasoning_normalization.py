"""Provider-neutral reasoning and answer normalization for complete and streamed responses."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

ReasoningEventKind = Literal["reasoning", "answer", "tool", "replay"]


@dataclass(frozen=True, slots=True)
class NormalizedContentEvent:
    kind: ReasoningEventKind
    text: str = ""
    data: Any = None


_FIELD_PRECEDENCE = (
    "reasoning_details",
    "reasoning_content",
    "reasoning",
    "thinking",
    "reasoning_text",
    "thinking_content",
    "thought",
    "thoughts",
)
_STRUCTURED_TYPES = {"reasoning", "reasoning_content", "thinking", "analysis"}
_TOOL_TYPES = {"tool", "tool_use", "tool_call"}
_TAG_PATTERN = re.compile(
    r"(?ms)(?P<prefix>\A|\n)[ \t]*<(?P<tag>think|thinking|reasoning|analysis)>"
    r"(?P<reasoning>.*?)</(?P=tag)>"
)


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dumped
    values = getattr(value, "__dict__", None)
    return values if isinstance(values, Mapping) else {}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_text(item) for item in value)
    data = _mapping(value)
    for key in ("text", "content", "reasoning_content", "reasoning", "thinking"):
        candidate = data.get(key)
        if isinstance(candidate, str):
            return candidate
    return ""


def _field_value(payload: Mapping[str, Any], name: str) -> Any:
    if name in payload:
        return payload[name]
    for container_name in ("additional_kwargs", "response_metadata", "model_extra"):
        container = _mapping(payload.get(container_name))
        if name in container:
            return container[name]
    return None


def _structured_content_events(content: Any) -> tuple[list[NormalizedContentEvent], bool]:
    if not isinstance(content, list):
        return [], False
    events: list[NormalizedContentEvent] = []
    has_reasoning = False
    for block in content:
        data = _mapping(block)
        block_type = str(data.get("type", "")).lower()
        block_text = _text(data)
        if block_type in _STRUCTURED_TYPES:
            has_reasoning = True
            if block_text:
                events.append(NormalizedContentEvent("reasoning", block_text, block))
        elif block_type in _TOOL_TYPES:
            events.append(NormalizedContentEvent("tool", data=block))
        elif block_text:
            events.append(NormalizedContentEvent("answer", block_text, block))
    return events, has_reasoning


def _tag_fallback(text: str) -> list[NormalizedContentEvent]:
    matches = list(_TAG_PATTERN.finditer(text))
    if not matches:
        return [NormalizedContentEvent("answer", text)] if text else []

    events: list[NormalizedContentEvent] = []
    cursor = 0
    for match in matches:
        answer = text[cursor : match.start()]
        if answer:
            events.append(NormalizedContentEvent("answer", answer))
        reasoning = match.group("reasoning")
        if reasoning:
            events.append(NormalizedContentEvent("reasoning", reasoning))
        cursor = match.end()
    if tail := text[cursor:]:
        events.append(NormalizedContentEvent("answer", tail))
    return events


def normalize_reasoning_content(payload: Any) -> list[NormalizedContentEvent]:
    """Normalize a complete provider message using deterministic source precedence."""
    data = _mapping(payload)
    content = data.get("content", "")
    structured_events, has_structured_reasoning = _structured_content_events(content)
    if has_structured_reasoning:
        return structured_events

    answer_text = _text(content)
    for field_name in _FIELD_PRECEDENCE:
        value = _field_value(data, field_name)
        reasoning_text = _text(value)
        if reasoning_text:
            events = [NormalizedContentEvent("reasoning", reasoning_text, value)]
            if answer_text:
                events.append(NormalizedContentEvent("answer", answer_text))
            return events
    return _tag_fallback(answer_text)


class ReasoningStreamNormalizer:
    """Accumulate arbitrary chunk boundaries and normalize once precedence is knowable."""

    def __init__(self) -> None:
        self._contents: list[Any] = []
        self._fields: dict[str, list[Any]] = {name: [] for name in _FIELD_PRECEDENCE}
        self._tool_blocks: list[Any] = []

    def feed(self, chunk: Any) -> list[NormalizedContentEvent]:
        """Consume a chunk.

        Events are intentionally held until ``finalize`` so a later higher-precedence
        structured field cannot duplicate or contradict an earlier tag fallback.
        """
        data = _mapping(chunk)
        content = data.get("content")
        if isinstance(content, list):
            self._contents.extend(content)
        elif isinstance(content, str):
            self._contents.append(content)
        for field_name in _FIELD_PRECEDENCE:
            value = _field_value(data, field_name)
            if value not in (None, "", []):
                self._fields[field_name].append(value)
        for tool_key in ("tool_calls", "tool_call_chunks"):
            value = data.get(tool_key)
            if isinstance(value, list):
                self._tool_blocks.extend(value)
        return []

    def finalize(self) -> list[NormalizedContentEvent]:
        list_content = [item for item in self._contents if not isinstance(item, str)]
        text_content = "".join(item for item in self._contents if isinstance(item, str))
        structured_events, has_structured_reasoning = _structured_content_events(list_content)
        if has_structured_reasoning:
            events = structured_events
            if text_content:
                events.append(NormalizedContentEvent("answer", text_content))
        else:
            events = []
            for field_name in _FIELD_PRECEDENCE:
                values = self._fields[field_name]
                reasoning_text = "".join(_text(value) for value in values)
                if reasoning_text:
                    events.append(NormalizedContentEvent("reasoning", reasoning_text, values))
                    if text_content:
                        events.append(NormalizedContentEvent("answer", text_content))
                    break
            else:
                events = _tag_fallback(text_content)
        events.extend(NormalizedContentEvent("tool", data=tool) for tool in self._tool_blocks)
        return events

    def reconcile_final(self, payload: Any) -> list[NormalizedContentEvent]:
        """Reconcile accumulated deltas with a final message without duplicating content."""
        return deduplicate_normalized_events(self.finalize(), normalize_reasoning_content(payload))


def deduplicate_normalized_events(
    streamed: list[NormalizedContentEvent], final: list[NormalizedContentEvent]
) -> list[NormalizedContentEvent]:
    """Prefer authoritative final events and retain stream-only ordered events once."""
    final_fingerprints = {(event.kind, event.text) for event in final if event.kind in {"reasoning", "answer"}}
    prefix = [
        event
        for event in streamed
        if event.kind not in {"reasoning", "answer"} or (event.kind, event.text) not in final_fingerprints
    ]
    result: list[NormalizedContentEvent] = []
    seen_display: set[tuple[str, str]] = set()
    for event in [*prefix, *final]:
        fingerprint = (event.kind, event.text)
        if event.kind in {"reasoning", "answer"}:
            if not event.text or fingerprint in seen_display:
                continue
            seen_display.add(fingerprint)
        result.append(event)
    return result
