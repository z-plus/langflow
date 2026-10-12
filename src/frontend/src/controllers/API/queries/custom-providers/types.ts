/** A discovered model entry stored on a custom provider. */
export type CustomProviderDiscoveredModel = {
  model_id: string;
  model_type: "llm" | "embeddings";
  name?: string;
};

/** A manually added model entry (typed llm by default on the backend). */
export type CustomProviderManualModel = {
  model_id: string;
  model_type?: "llm" | "embeddings";
  name?: string;
};

export type CustomProviderValidationStatus = "draft" | "valid" | "invalid";

/** Shape of `provider_read` from GET /api/v1/custom-providers.* */
export type CustomProvider = {
  id: string;
  user_id: string;
  provider_id: string;
  display_name: string;
  base_url: string;
  has_api_key: boolean;
  validation_status: CustomProviderValidationStatus;
  validation_error?: string | null;
  last_validated_at?: string | null;
  discovered_models: CustomProviderDiscoveredModel[];
  manual_models: CustomProviderManualModel[];
  created_at?: string;
  updated_at?: string;
};

export interface CustomProviderCreateRequest {
  provider_id: string;
  display_name: string;
  base_url: string;
  api_key: string;
  discovered_models?: CustomProviderDiscoveredModel[];
  manual_models?: CustomProviderManualModel[];
}

export interface CustomProviderUpdateRequest {
  display_name?: string;
  base_url?: string;
  api_key?: string;
}

/** Response of the no-persistence connection probe (POST /meta/preview). */
export interface CustomProviderPreview {
  valid: boolean;
  error?: string | null;
  models: { llm: string[]; embeddings: string[] };
}
