import type { useMutationFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { CustomProviderPreview } from "./types";

interface PreviewCustomProviderParams {
  base_url: string;
  api_key: string;
}

export const usePostCustomProviderPreview: useMutationFunctionType<
  undefined,
  PreviewCustomProviderParams,
  CustomProviderPreview
> = (options?) => {
  const { mutate } = UseRequestProcessor();
  return mutate(
    ["usePostCustomProviderPreview"],
    async (payload) => {
      const res = await api.post<CustomProviderPreview>(
        `${getURL("CUSTOM_PROVIDERS")}/meta/preview`,
        payload,
      );
      return res.data;
    },
    options,
  );
};
