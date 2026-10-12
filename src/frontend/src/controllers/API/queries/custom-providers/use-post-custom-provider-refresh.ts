import type { useMutationFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { CustomProvider } from "./types";

export const usePostCustomProviderRefresh: useMutationFunctionType<
  undefined,
  { provider_id: string },
  CustomProvider
> = (options?) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["usePostCustomProviderRefresh"],
    async ({ provider_id }) => {
      const res = await api.post<CustomProvider>(
        `${getURL("CUSTOM_PROVIDERS")}/${provider_id}/refresh`,
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
