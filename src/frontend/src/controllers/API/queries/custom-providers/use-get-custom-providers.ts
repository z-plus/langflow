import { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { CustomProvider } from "./types";

export const useGetCustomProviders: useQueryFunctionType<
  { search?: string } | undefined,
  CustomProvider[]
> = (params, options?) => {
  const { query } = UseRequestProcessor();
  const search = params?.search?.trim();
  const queryParams = search ? `?search=${encodeURIComponent(search)}` : "";
  return query(
    ["useGetCustomProviders", search ?? ""],
    async () => {
      const res = await api.get<CustomProvider[]>(
        `${getURL("CUSTOM_PROVIDERS")}${queryParams}`,
      );
      return res.data;
    },
    options,
  );
};
