import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const createProvider = jest.fn();
const updateProvider = jest.fn();
const deleteProvider = jest.fn();
const refreshModels = jest.fn();
const addModel = jest.fn();
const removeModel = jest.fn();
const updateEnabledModels = jest.fn();
const refetchEnabledModels = jest.fn();
const refetchProviders = jest.fn();

const provider = {
  id: "provider-1",
  name: "Company Gateway",
  base_url: "https://llm.example/v1",
  has_api_key: true,
  is_verified: false,
  verification_error: "The models endpoint returned 404",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

let providersResult: Record<string, unknown>;
let modelsResult: Record<string, unknown>;

jest.mock(
  "@/controllers/API/queries/custom-model-providers/use-custom-model-providers",
  () => ({
    useGetCustomModelProviders: () => providersResult,
    useGetCustomProviderModels: () => modelsResult,
    useCreateCustomModelProvider: () => ({
      mutateAsync: createProvider,
      isPending: false,
    }),
    useUpdateCustomModelProvider: () => ({
      mutateAsync: updateProvider,
      isPending: false,
    }),
    useDeleteCustomModelProvider: () => ({
      mutateAsync: deleteProvider,
      isPending: false,
    }),
    useRefreshCustomProviderModels: () => ({
      mutateAsync: refreshModels,
      isPending: false,
    }),
    useAddCustomProviderModel: () => ({
      mutateAsync: addModel,
      isPending: false,
    }),
    useDeleteCustomProviderModel: () => ({
      mutateAsync: removeModel,
      isPending: false,
    }),
  }),
);

jest.mock("@/components/common/genericIconComponent", () => ({
  __esModule: true,
  default: ({ name }: { name: string }) => (
    <span aria-hidden="true">{name}</span>
  ),
}));

jest.mock("@/controllers/API/queries/models/use-get-enabled-models", () => ({
  useGetEnabledModels: () => ({
    data: {
      enabled_models: {
        "custom-openai-compatible:provider-1": { qwen3: true },
      },
    },
    isLoading: false,
    refetch: refetchEnabledModels,
  }),
}));

jest.mock("@/controllers/API/queries/models/use-update-enabled-models", () => ({
  useUpdateEnabledModels: () => ({
    mutateAsync: updateEnabledModels,
    isPending: false,
  }),
}));

import CustomModelProvidersPanel from "../components/CustomModelProvidersPanel";

describe("CustomModelProvidersPanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    createProvider.mockResolvedValue(provider);
    updateProvider.mockResolvedValue(provider);
    deleteProvider.mockResolvedValue(undefined);
    refreshModels.mockResolvedValue([]);
    addModel.mockResolvedValue({});
    removeModel.mockResolvedValue(undefined);
    updateEnabledModels.mockResolvedValue({ disabled_models: [] });
    refetchEnabledModels.mockResolvedValue({});
    providersResult = {
      data: [provider],
      isLoading: false,
      isError: false,
      refetch: refetchProviders,
    };
    modelsResult = {
      data: [
        {
          id: "model-1",
          model_id: "qwen3",
          manually_added: true,
          discovered: false,
          available: true,
          last_discovered_at: null,
        },
      ],
      isLoading: false,
      isError: false,
    };
  });

  it("shows discovery failure and permits manual entry while preserving manual models on refresh", async () => {
    const user = userEvent.setup();
    render(<CustomModelProvidersPanel />);

    expect(
      screen.getByText("The models endpoint returned 404"),
    ).toBeInTheDocument();
    expect(screen.getByText("qwen3")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Manual model ID"), "deepseek-r1");
    await user.click(screen.getByRole("button", { name: "Add Model" }));
    expect(addModel).toHaveBeenCalledWith("deepseek-r1");

    await user.click(
      screen.getByRole("button", {
        name: "Refresh models for Company Gateway",
      }),
    );
    expect(refreshModels).toHaveBeenCalledTimes(1);
    expect(screen.getByText("qwen3")).toBeInTheDocument();
  });

  it("updates model status with the stable custom provider identity", async () => {
    const user = userEvent.setup();
    render(<CustomModelProvidersPanel />);

    await user.click(screen.getByTestId("custom-model-toggle-model-1"));

    expect(updateEnabledModels).toHaveBeenCalledWith({
      updates: [
        {
          provider: "custom-openai-compatible:provider-1",
          model_id: "qwen3",
          model_type: "llm",
          enabled: false,
        },
      ],
    });
  });

  it("keeps the saved key masked and omits it when editing", async () => {
    const user = userEvent.setup();
    render(<CustomModelProvidersPanel />);

    await user.click(
      screen.getByRole("button", { name: "Edit Company Gateway" }),
    );
    expect(screen.getByText(/A key is saved/)).toBeInTheDocument();
    expect(screen.getByLabelText("API key")).toHaveValue("");

    await user.clear(screen.getByLabelText("Provider name"));
    await user.type(screen.getByLabelText("Provider name"), "Renamed Gateway");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateProvider).toHaveBeenCalledWith({
      name: "Renamed Gateway",
      base_url: "https://llm.example/v1",
    });
  });

  it("surfaces case-insensitive name conflicts from the API", async () => {
    const user = userEvent.setup();
    createProvider.mockRejectedValue(
      new Error("Custom provider name already exists"),
    );
    render(<CustomModelProvidersPanel />);

    await user.click(screen.getByRole("button", { name: "Add provider" }));
    await user.type(screen.getByLabelText("Provider name"), "company gateway");
    await user.type(
      screen.getByLabelText("Base URL"),
      "https://other.example/v1",
    );
    await user.type(screen.getByLabelText("API key"), "secret");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Custom provider name already exists",
    );
  });

  it("warns before soft deletion", async () => {
    const user = userEvent.setup();
    render(<CustomModelProvidersPanel />);

    await user.click(
      screen.getByRole("button", { name: "Delete Company Gateway" }),
    );
    expect(
      screen.getByText(/Saved flows will keep the provider reference/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete Provider" }));
    expect(deleteProvider).toHaveBeenCalledWith("provider-1");
  });

  it("opens the create dialog from the keyboard", async () => {
    const user = userEvent.setup();
    render(<CustomModelProvidersPanel />);
    const addButton = screen.getByRole("button", { name: "Add provider" });
    addButton.focus();

    await user.keyboard("{Enter}");

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText("Provider name")).toBeRequired();
    expect(screen.getByLabelText("API key")).toBeRequired();
  });

  it("renders loading and recoverable error states", async () => {
    providersResult = {
      isLoading: true,
      isError: false,
      refetch: refetchProviders,
    };
    const { rerender } = render(<CustomModelProvidersPanel />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading providers");

    providersResult = {
      isLoading: false,
      isError: true,
      refetch: refetchProviders,
    };
    rerender(<CustomModelProvidersPanel />);
    expect(screen.getByRole("alert")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(refetchProviders).toHaveBeenCalledTimes(1));
  });
});
