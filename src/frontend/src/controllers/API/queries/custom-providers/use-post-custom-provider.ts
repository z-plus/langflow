import type { useMutationFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { CustomProvider, CustomProviderCreateRequest } from "./types";

export const usePostCustomProvider: useMutationFunctionType<
  undefined,
  CustomProviderCreateRequest,
  CustomProvider
> = (options?) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["usePostCustomProvider"],
    async (payload) => {
      const res = await api.post<CustomProvider>(
        `${getURL("CUSTOM_PROVIDERS")}`,
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
