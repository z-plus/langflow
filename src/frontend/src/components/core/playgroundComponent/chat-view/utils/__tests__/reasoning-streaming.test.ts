import { queryClient } from "@/contexts";
import type { ContentBlockItem, ReasoningContent } from "@/types/chat";
import type { Message } from "@/types/messages";
import { updateMessage } from "../message-utils";

const QUERY_KEY = ["useGetMessagesQuery", { id: "flow-1", session_id: "s1" }];

function buildMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: "msg-1",
    text: "",
    sender: "Machine",
    sender_name: "AI",
    session_id: "s1",
    flow_id: "flow-1",
    timestamp: new Date().toISOString(),
    files: [],
    ...overrides,
  } as Message;
}

beforeEach(() => {
  queryClient.clear();
});

const reasoningBlock = (overrides: Partial<ReasoningContent> = {}): ReasoningContent => ({
  type: "reasoning",
  text: "Considering options…",
  ...overrides,
});

describe("reasoning streaming reconciliation", () => {
  it("preserves provider_data on reasoning blocks through streaming partials", () => {
    // First the backend emits a complete add_message event carrying the
    // reasoning block plus the bounded provider-native replay payload.
    const initialBlocks: ContentBlockItem[] = [
      reasoningBlock({
        provider_data: { reasoning_details: [{ type: "reasoning.text", text: "…" }] },
      }),
    ];
    updateMessage(
      buildMessage({
        id: "msg-1",
        text: "",
        content_blocks: initialBlocks,
      }),
    );

    // The next event is a token event (state: "partial") that does not
    // carry content_blocks. Existing block list must survive untouched
    // so the replay payload is intact for the next request.
    updateMessage(
      buildMessage({
        id: "msg-1",
        text: "Hello",
        content_blocks: undefined,
        properties: { state: "partial" } as Message["properties"],
      }),
    );

    const persisted = queryClient.getQueryData<Message[]>(QUERY_KEY)!;
    const reasoning = persisted[0].content_blocks?.[0] as ReasoningContent;
    expect(reasoning.type).toBe("reasoning");
    expect(reasoning.text).toBe("Considering options…");
    expect(reasoning.provider_data).toEqual({
      reasoning_details: [{ type: "reasoning.text", text: "…" }],
    });
  });

  it("merges incremental reasoning text into a final complete add_message", () => {
    // A first partial (text-only) seeds the streaming message.
    updateMessage(
      buildMessage({
        id: "msg-1",
        text: "Hello",
        content_blocks: undefined,
        properties: { state: "partial" } as Message["properties"],
      }),
    );

    // The final add_message event arrives with the normalized reasoning
    // block — including its replay payload — and no streaming flag.
    const finalBlocks: ContentBlockItem[] = [
      reasoningBlock({
        text: "Considering options…",
        provider_data: { reasoning_details: [{ type: "reasoning.text", text: "considering" }] },
      }),
    ];
    updateMessage(
      buildMessage({
        id: "msg-1",
        text: "Hello",
        content_blocks: finalBlocks,
      }),
    );

    const persisted = queryClient.getQueryData<Message[]>(QUERY_KEY)!;
    expect(persisted).toHaveLength(1);
    expect(persisted[0].text).toBe("Hello");
    const reasoning = persisted[0].content_blocks?.[0] as ReasoningContent;
    expect(reasoning.provider_data).toEqual({
      reasoning_details: [{ type: "reasoning.text", text: "considering" }],
    });
  });

  it("preserves provider_data when reloaded from the persisted history", () => {
    // Reload path bypasses streaming — a fresh setQueryData with the
    // already-normalized content_blocks. The opaque payload must still
    // round-trip because the next request may need it for replay.
    const historyBlocks: ContentBlockItem[] = [
      reasoningBlock({
        provider_data: {
          reasoning_details: [
            { type: "reasoning.encrypted", ciphertext: "0xDEADBEEF" },
          ],
        },
      }),
    ];
    queryClient.setQueryData<Message[]>(QUERY_KEY, [
      buildMessage({ id: "msg-1", content_blocks: historyBlocks }),
    ]);

    const reloaded = queryClient.getQueryData<Message[]>(QUERY_KEY)!;
    const reasoning = reloaded[0].content_blocks?.[0] as ReasoningContent;
    expect(reasoning.provider_data).toEqual({
      reasoning_details: [
        { type: "reasoning.encrypted", ciphertext: "0xDEADBEEF" },
      ],
    });
  });

  it("keeps reasoning, tool_use, and text in producer order across updates", () => {
    // The first add_message announces the reasoning step (no tool yet).
    updateMessage(
      buildMessage({
        id: "msg-1",
        text: "",
        content_blocks: [
          reasoningBlock({ text: "find data", provider_data: { reasoning_details: [] } }),
        ],
      }),
    );

    // The follow-up add_message interleaves the tool and the final answer
    // text. The cached reasoning block is dropped because the new
    // content_blocks array carries the full producer order.
    updateMessage(
      buildMessage({
        id: "msg-1",
        text: "done",
        content_blocks: [
          reasoningBlock({ text: "find data", provider_data: { reasoning_details: [] } }),
          {
            type: "tool_use",
            name: "search",
            tool_input: { q: "weather" },
          },
          { type: "text", text: "It is sunny." },
        ],
      }),
    );

    const persisted = queryClient.getQueryData<Message[]>(QUERY_KEY)!;
    const types = persisted[0].content_blocks?.map((b) => b.type);
    expect(types).toEqual(["reasoning", "tool_use", "text"]);
    const reasoning = persisted[0].content_blocks?.[0] as ReasoningContent;
    expect(reasoning.provider_data).toEqual({ reasoning_details: [] });
  });
});
