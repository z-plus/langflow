import type { useMutationFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { CustomProvider } from "./types";

interface AddCustomProviderModelParams {
  provider_id: string;
  payload: { model_id: string; name?: string };
}

export const usePostCustomProviderModel: useMutationFunctionType<
  undefined,
  AddCustomProviderModelParams,
  CustomProvider
> = (options?) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["usePostCustomProviderModel"],
    async ({ provider_id, payload }) => {
      const res = await api.post<CustomProvider>(
        `${getURL("CUSTOM_PROVIDERS")}/${provider_id}/models`,
        payload,
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
