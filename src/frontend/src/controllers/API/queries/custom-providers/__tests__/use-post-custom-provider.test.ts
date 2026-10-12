const mockApiPost = jest.fn();
const mockQueryClient = {
  refetchQueries: jest.fn(),
  invalidateQueries: jest.fn(),
};

jest.mock("@/controllers/API/api", () => ({
  api: { post: mockApiPost },
}));

jest.mock("@/controllers/API/helpers/constants", () => ({
  getURL: jest.fn(() => "/api/v1/custom-providers"),
}));

const mockMutate = jest.fn(
  // biome-ignore lint/suspicious/noExplicitAny: test mock
  (_key: any, fn: any, options: any) => ({
    // biome-ignore lint/suspicious/noExplicitAny: test mock
    mutate: async (payload: any) => {
      const result = await fn(payload);
      options?.onSuccess?.(result, payload);
      return result;
    },
  }),
);

jest.mock("@/controllers/API/services/request-processor", () => ({
  UseRequestProcessor: jest.fn(() => ({
    mutate: mockMutate,
    queryClient: mockQueryClient,
  })),
}));

import type { CustomProviderCreateRequest } from "../types";
import { usePostCustomProvider } from "../use-post-custom-provider";

describe("usePostCustomProvider", () => {
  beforeEach(() => jest.clearAllMocks());

  const validPayload: CustomProviderCreateRequest = {
    provider_id: "mygateway",
    display_name: "My Gateway",
    base_url: "https://gw.example.com/v1",
    api_key: "secret-key", // pragma: allowlist secret
    discovered_models: [],
    manual_models: [],
  };

  it("posts to the custom-providers endpoint with the payload", async () => {
    mockApiPost.mockResolvedValue({
      data: { id: "prov-1", provider_id: "mygateway" },
    });

    const mutation = usePostCustomProvider();
    await mutation.mutate(validPayload);

    expect(mockApiPost).toHaveBeenCalledWith(
      "/api/v1/custom-providers",
      validPayload,
    );
  });

  it("sends the api_key so it is stored server-side (never read back)", async () => {
    mockApiPost.mockResolvedValue({ data: { id: "prov-1" } });

    const mutation = usePostCustomProvider();
    await mutation.mutate(validPayload);

    expect(mockApiPost.mock.calls[0][1].api_key).toBe("secret-key");
  });

  it("invalidates the custom-provider list AND the merged model-provider list", async () => {
    mockApiPost.mockResolvedValue({ data: { id: "prov-1" } });

    const mutation = usePostCustomProvider();
    await mutation.mutate(validPayload);

    expect(mockQueryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["useGetCustomProviders"],
    });
    expect(mockQueryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["useGetModelProviders"],
    });
  });

  it("returns the created provider", async () => {
    const created = {
      id: "prov-1",
      provider_id: "mygateway",
      display_name: "My Gateway",
    };
    mockApiPost.mockResolvedValue({ data: created });

    const mutation = usePostCustomProvider();
    const result = await mutation.mutate(validPayload);

    expect(result).toEqual(created);
  });
});
