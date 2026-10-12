import type { useMutationFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { CustomProvider, CustomProviderUpdateRequest } from "./types";

interface PatchCustomProviderParams {
  provider_id: string;
  payload: CustomProviderUpdateRequest;
}

export const usePatchCustomProvider: useMutationFunctionType<
  undefined,
  PatchCustomProviderParams,
  CustomProvider
> = (options?) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["usePatchCustomProvider"],
    async ({ provider_id, payload }) => {
      const res = await api.patch<CustomProvider>(
        `${getURL("CUSTOM_PROVIDERS")}/${provider_id}`,
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
