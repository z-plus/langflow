import { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { ModelProviderInfo } from "../models/use-get-model-providers";

/** Catalog-shaped supplier entries (provider=provider_id, custom=true). */
export const useGetCustomProviderCatalog: useQueryFunctionType<
  undefined,
  ModelProviderInfo[]
> = (options?) => {
  const { query } = UseRequestProcessor();
  return query(
    ["useGetCustomProviderCatalog"],
    async () => {
      const res = await api.get<ModelProviderInfo[]>(
        `${getURL("CUSTOM_PROVIDERS")}/catalog`,
      );
      return res.data;
    },
    options,
  );
};
