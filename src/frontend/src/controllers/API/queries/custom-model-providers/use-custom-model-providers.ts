import type { QueryClient } from "@tanstack/react-query";
import type {
  useMutationFunctionType,
  useQueryFunctionType,
} from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export interface CustomModelProvider {
  id: string;
  name: string;
  base_url: string;
  has_api_key: boolean;
  is_verified: boolean;
  verification_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomModelProviderModel {
  id: string;
  model_id: string;
  manually_added: boolean;
  discovered: boolean;
  available: boolean;
  last_discovered_at: string | null;
}

export interface CustomModelProviderCreate {
  name: string;
  base_url: string;
  api_key: string;
}

export interface CustomModelProviderUpdate {
  name?: string;
  base_url?: string;
  api_key?: string;
}

const providersKey = ["useGetCustomModelProviders"] as const;
const modelsKey = (providerId: string) =>
  ["useGetCustomProviderModels", providerId] as const;

const invalidateCustomProviderQueries = (
  queryClient: QueryClient,
  providerId?: string,
) => {
  queryClient.invalidateQueries({ queryKey: providersKey });
  queryClient.invalidateQueries({
    queryKey: providerId
      ? modelsKey(providerId)
      : ["useGetCustomProviderModels"],
  });
  queryClient.invalidateQueries({
    queryKey: ["useGetModelProviders"],
    refetchType: "none",
  });
  queryClient.invalidateQueries({ queryKey: ["useGetEnabledModels"] });
  queryClient.invalidateQueries({ queryKey: ["useGetProviderVariables"] });
};

export const useGetCustomModelProviders: useQueryFunctionType<
  undefined,
  CustomModelProvider[]
> = (options) => {
  const { query } = UseRequestProcessor();
  return query(
    providersKey,
    async () =>
      (await api.get<CustomModelProvider[]>(getURL("CUSTOM_MODEL_PROVIDERS")))
        .data,
    options,
  );
};

export const useGetCustomProviderModels: useQueryFunctionType<
  string,
  CustomModelProviderModel[]
> = (providerId, options) => {
  const { query } = UseRequestProcessor();
  return query(
    modelsKey(providerId),
    async () =>
      (
        await api.get<CustomModelProviderModel[]>(
          `${getURL("CUSTOM_MODEL_PROVIDERS")}/${providerId}/models`,
        )
      ).data,
    options,
  );
};

export const useCreateCustomModelProvider: useMutationFunctionType<
  undefined,
  CustomModelProviderCreate,
  CustomModelProvider
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useCreateCustomModelProvider"],
    async (payload) =>
      (
        await api.post<CustomModelProvider>(
          getURL("CUSTOM_MODEL_PROVIDERS"),
          payload,
        )
      ).data,
    {
      retry: false,
      onSettled: () => invalidateCustomProviderQueries(queryClient),
      ...options,
    },
  );
};

export const useUpdateCustomModelProvider: useMutationFunctionType<
  string,
  CustomModelProviderUpdate,
  CustomModelProvider
> = (providerId, options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useUpdateCustomModelProvider", providerId],
    async (payload) =>
      (
        await api.patch<CustomModelProvider>(
          `${getURL("CUSTOM_MODEL_PROVIDERS")}/${providerId}`,
          payload,
        )
      ).data,
    {
      retry: false,
      onSettled: () => invalidateCustomProviderQueries(queryClient, providerId),
      ...options,
    },
  );
};

export const useDeleteCustomModelProvider: useMutationFunctionType<
  undefined,
  string,
  void
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useDeleteCustomModelProvider"],
    async (providerId) => {
      await api.delete(`${getURL("CUSTOM_MODEL_PROVIDERS")}/${providerId}`);
    },
    {
      retry: false,
      onSettled: (_data, _error, providerId) =>
        invalidateCustomProviderQueries(queryClient, providerId),
      ...options,
    },
  );
};

export const useRefreshCustomProviderModels: useMutationFunctionType<
  string,
  void,
  CustomModelProviderModel[]
> = (providerId, options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useRefreshCustomProviderModels", providerId],
    async () =>
      (
        await api.post<CustomModelProviderModel[]>(
          `${getURL("CUSTOM_MODEL_PROVIDERS")}/${providerId}/refresh`,
        )
      ).data,
    {
      retry: false,
      onSettled: () => invalidateCustomProviderQueries(queryClient, providerId),
      ...options,
    },
  );
};

export const useAddCustomProviderModel: useMutationFunctionType<
  string,
  string,
  CustomModelProviderModel
> = (providerId, options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useAddCustomProviderModel", providerId],
    async (modelId) =>
      (
        await api.post<CustomModelProviderModel>(
          `${getURL("CUSTOM_MODEL_PROVIDERS")}/${providerId}/models`,
          { model_id: modelId },
        )
      ).data,
    {
      retry: false,
      onSettled: () => invalidateCustomProviderQueries(queryClient, providerId),
      ...options,
    },
  );
};

export const useDeleteCustomProviderModel: useMutationFunctionType<
  string,
  string,
  void
> = (providerId, options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useDeleteCustomProviderModel", providerId],
    async (modelId) => {
      await api.delete(
        `${getURL("CUSTOM_MODEL_PROVIDERS")}/${providerId}/models/${encodeURIComponent(modelId)}`,
      );
    },
    {
      retry: false,
      onSettled: () => invalidateCustomProviderQueries(queryClient, providerId),
      ...options,
    },
  );
};
