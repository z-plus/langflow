import type { useMutationFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { CustomProvider } from "./types";

interface DeleteCustomProviderModelParams {
  provider_id: string;
  model_id: string;
}

export const useDeleteCustomProviderModel: useMutationFunctionType<
  undefined,
  DeleteCustomProviderModelParams,
  CustomProvider
> = (options?) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useDeleteCustomProviderModel"],
    async ({ provider_id, model_id }) => {
      const res = await api.delete<CustomProvider>(
        `${getURL("CUSTOM_PROVIDERS")}/${provider_id}/models/${model_id}`,
      );
      return res.data;
    },
    {
      ...options,
      onSuccess: (...args) => {
        queryClient.invalidateQueries({ queryKey: ["useGetCustomProviders"] });
        queryClient.invalidateQueries({ queryKey: ["useGetModelProviders"] });
        options?.onSuccess?.(...args);
      },
    },
  );
};
