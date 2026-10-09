const mockApi = {
  get: jest.fn(),
  post: jest.fn(),
  patch: jest.fn(),
  delete: jest.fn(),
};
const mockQueryClient = { invalidateQueries: jest.fn() };
const mockQuery = jest.fn(
  // biome-ignore lint/suspicious/noExplicitAny: test adapter
  (key: any, fn: any, options: any) => ({ key, fn, options }),
);
const mockMutate = jest.fn(
  // biome-ignore lint/suspicious/noExplicitAny: test adapter
  (key: any, fn: any, options: any) => ({
    key,
    options,
    // biome-ignore lint/suspicious/noExplicitAny: test adapter
    mutate: async (variables: any) => {
      let data;
      let error;
      try {
        data = await fn(variables);
        return data;
      } catch (caught) {
        error = caught;
        throw caught;
      } finally {
        options?.onSettled?.(data, error, variables);
      }
    },
  }),
);

jest.mock("@/controllers/API/api", () => ({ api: mockApi }));
jest.mock("@/controllers/API/helpers/constants", () => ({
  getURL: jest.fn(() => "/api/v1/models/custom-providers"),
}));
jest.mock("@/controllers/API/services/request-processor", () => ({
  UseRequestProcessor: () => ({
    query: mockQuery,
    mutate: mockMutate,
    queryClient: mockQueryClient,
  }),
}));

import {
  useAddCustomProviderModel,
  useCreateCustomModelProvider,
  useDeleteCustomModelProvider,
  useDeleteCustomProviderModel,
  useGetCustomModelProviders,
  useGetCustomProviderModels,
  useRefreshCustomProviderModels,
  useUpdateCustomModelProvider,
} from "../use-custom-model-providers";

describe("custom model provider API hooks", () => {
  beforeEach(() => jest.clearAllMocks());

  it("queries provider and provider-scoped model lists", async () => {
    mockApi.get
      .mockResolvedValueOnce({ data: [{ id: "provider-1" }] })
      .mockResolvedValueOnce({ data: [{ model_id: "model-1" }] });

    const providers = useGetCustomModelProviders() as unknown as {
      fn: () => Promise<unknown>;
    };
    const models = useGetCustomProviderModels("provider-1") as unknown as {
      fn: () => Promise<unknown>;
    };

    await expect(providers.fn()).resolves.toEqual([{ id: "provider-1" }]);
    await expect(models.fn()).resolves.toEqual([{ model_id: "model-1" }]);
    expect(mockQuery.mock.calls[1][0]).toEqual([
      "useGetCustomProviderModels",
      "provider-1",
    ]);
    expect(mockApi.get).toHaveBeenLastCalledWith(
      "/api/v1/models/custom-providers/provider-1/models",
    );
  });

  it("sends create and update payloads without inventing a replacement key", async () => {
    mockApi.post.mockResolvedValue({ data: { id: "provider-1" } });
    mockApi.patch.mockResolvedValue({ data: { id: "provider-1" } });
    const createPayload = {
      name: "Local",
      base_url: "https://llm.example/v1",
      api_key: "secret", // pragma: allowlist secret
    };
    const updatePayload = { name: "Renamed" };

    await useCreateCustomModelProvider().mutate(createPayload);
    await useUpdateCustomModelProvider("provider-1").mutate(updatePayload);

    expect(mockApi.post).toHaveBeenCalledWith(
      "/api/v1/models/custom-providers",
      createPayload,
    );
    expect(mockApi.patch).toHaveBeenCalledWith(
      "/api/v1/models/custom-providers/provider-1",
      updatePayload,
    );
    expect(mockApi.patch.mock.calls[0][1]).not.toHaveProperty("api_key");
  });

  it("uses the refresh and manual model endpoints", async () => {
    mockApi.post
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: { model_id: "org/model one" } });
    mockApi.delete.mockResolvedValue({});

    await useRefreshCustomProviderModels("provider-1").mutate();
    await useAddCustomProviderModel("provider-1").mutate("org/model one");
    await useDeleteCustomProviderModel("provider-1").mutate("org/model one");
    await useDeleteCustomModelProvider().mutate("provider-1");

    expect(mockApi.post).toHaveBeenNthCalledWith(
      1,
      "/api/v1/models/custom-providers/provider-1/refresh",
    );
    expect(mockApi.post).toHaveBeenNthCalledWith(
      2,
      "/api/v1/models/custom-providers/provider-1/models",
      { model_id: "org/model one" },
    );
    expect(mockApi.delete).toHaveBeenNthCalledWith(
      1,
      "/api/v1/models/custom-providers/provider-1/models/org%2Fmodel%20one",
    );
    expect(mockApi.delete).toHaveBeenNthCalledWith(
      2,
      "/api/v1/models/custom-providers/provider-1",
    );
  });

  it("propagates API errors and still invalidates scoped dependent caches", async () => {
    const error = new Error("discovery failed");
    mockApi.post.mockRejectedValue(error);

    await expect(
      useRefreshCustomProviderModels("provider-1").mutate(),
    ).rejects.toBe(error);

    expect(mockQueryClient.invalidateQueries.mock.calls).toEqual([
      [{ queryKey: ["useGetCustomModelProviders"] }],
      [{ queryKey: ["useGetCustomProviderModels", "provider-1"] }],
      [{ queryKey: ["useGetModelProviders"], refetchType: "none" }],
      [{ queryKey: ["useGetEnabledModels"] }],
      [{ queryKey: ["useGetProviderVariables"] }],
    ]);
  });

  it("disables retries for every mutation", () => {
    useCreateCustomModelProvider();
    useUpdateCustomModelProvider("provider-1");
    useDeleteCustomModelProvider();
    useRefreshCustomProviderModels("provider-1");
    useAddCustomProviderModel("provider-1");
    useDeleteCustomProviderModel("provider-1");

    expect(mockMutate.mock.calls.every((call) => call[2].retry === false)).toBe(
      true,
    );
  });
});
