import type { useMutationFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export const useDeleteCustomProvider: useMutationFunctionType<
  undefined,
  { provider_id: string }
> = (options?) => {
  const { mutate, queryClient } = UseRequestProcessor();
  return mutate(
    ["useDeleteCustomProvider"],
    async ({ provider_id }) => {
      await api.delete(`${getURL("CUSTOM_PROVIDERS")}/${provider_id}`);
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
