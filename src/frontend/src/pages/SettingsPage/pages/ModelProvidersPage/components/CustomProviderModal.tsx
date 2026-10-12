import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ForwardedIconComponent } from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  useDeleteCustomProviderModel,
  usePatchCustomProvider,
  usePostCustomProvider,
  usePostCustomProviderModel,
  usePostCustomProviderPreview,
} from "@/controllers/API/queries/custom-providers";
import type {
  CustomProvider,
  CustomProviderDiscoveredModel,
  CustomProviderManualModel,
} from "@/controllers/API/queries/custom-providers/types";
import { cn } from "@/utils/utils";

interface CustomProviderModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When provided the modal edits it; otherwise it creates a new supplier. */
  provider?: CustomProvider | null;
}

const getDetail = (err: unknown): string | null => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  return typeof detail === "string" ? detail : null;
};

export default function CustomProviderModal({
  open,
  onOpenChange,
  provider,
}: CustomProviderModalProps) {
  const { t } = useTranslation();
  const isEdit = !!provider;

  const [providerId, setProviderId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [discovered, setDiscovered] = useState<CustomProviderDiscoveredModel[]>(
    [],
  );
  const [manual, setManual] = useState<CustomProviderManualModel[]>([]);
  const [preview, setPreview] = useState<{
    error?: string | null;
    models: { llm: string[]; embeddings: string[] };
  } | null>(null);
  const [manualModelId, setManualModelId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { mutate: previewMutation, isPending: isPreviewing } =
    usePostCustomProviderPreview();
  const { mutateAsync: create, isPending: isCreating } =
    usePostCustomProvider();
  const { mutateAsync: update, isPending: isUpdating } =
    usePatchCustomProvider();
  const { mutateAsync: addManual, isPending: isAddingManual } =
    usePostCustomProviderModel();
  const { mutateAsync: removeManual, isPending: isRemovingManual } =
    useDeleteCustomProviderModel();

  useEffect(() => {
    if (!open) return;
    setProviderId(provider?.provider_id ?? "");
    setDisplayName(provider?.display_name ?? "");
    setBaseUrl(provider?.base_url ?? "");
    setApiKey("");
    setDiscovered(provider?.discovered_models ?? []);
    setManual(provider?.manual_models ?? []);
    setPreview(null);
    setManualModelId("");
    setError(null);
  }, [open, provider]);

  const canPreview = baseUrl.trim().length > 0 && apiKey.length > 0;
  const canSave =
    displayName.trim().length > 0 &&
    baseUrl.trim().length > 0 &&
    (isEdit || (providerId.trim().length > 0 && apiKey.length > 0));

  const handlePreview = () => {
    setError(null);
    previewMutation(
      { base_url: baseUrl.trim(), api_key: apiKey },
      {
        onSuccess: (res) => {
          setPreview(
            res.valid
              ? { error: null, models: res.models }
              : {
                  error: res.error ?? t("customProviders.previewFailed"),
                  models: { llm: [], embeddings: [] },
                },
          );
        },
        onError: (err) => setError(getDetail(err)),
      },
    );
  };

  const toggleDiscovered = (
    modelId: string,
    modelType: "llm" | "embeddings",
  ) => {
    setDiscovered((prev) =>
      prev.some((m) => m.model_id === modelId)
        ? prev.filter((m) => m.model_id !== modelId)
        : [...prev, { model_id: modelId, model_type: modelType }],
    );
  };

  const handleAddManual = async () => {
    const mid = manualModelId.trim();
    if (!mid) return;
    if (
      discovered.some((m) => m.model_id === mid) ||
      manual.some((m) => m.model_id === mid)
    ) {
      setError(t("customProviders.modelAlreadyExists", { model: mid }));
      return;
    }
    if (isEdit && provider) {
      try {
        await addManual({
          provider_id: provider.provider_id,
          payload: { model_id: mid },
        });
        setManualModelId("");
      } catch (err) {
        setError(getDetail(err));
      }
    } else {
      setManual((prev) => [...prev, { model_id: mid }]);
      setManualModelId("");
    }
  };

  const handleRemoveManual = async (modelId: string) => {
    if (isEdit && provider) {
      try {
        await removeManual({
          provider_id: provider.provider_id,
          model_id: modelId,
        });
      } catch (err) {
        setError(getDetail(err));
      }
    } else {
      setManual((prev) => prev.filter((m) => m.model_id !== modelId));
    }
  };

  const handleSave = async () => {
    setError(null);
    try {
      if (isEdit && provider) {
        const payload: {
          display_name?: string;
          base_url?: string;
          api_key?: string;
        } = {};
        if (displayName.trim() !== provider.display_name) {
          payload.display_name = displayName.trim();
        }
        if (baseUrl.trim() !== provider.base_url) {
          payload.base_url = baseUrl.trim();
        }
        if (apiKey.length > 0) {
          payload.api_key = apiKey;
        }
        await update({ provider_id: provider.provider_id, payload });
      } else {
        await create({
          provider_id: providerId.trim(),
          display_name: displayName.trim(),
          base_url: baseUrl.trim(),
          api_key: apiKey,
          discovered_models: discovered,
          manual_models: manual,
        });
      }
      onOpenChange(false);
    } catch (err) {
      setError(getDetail(err));
    }
  };

  const pending =
    isCreating ||
    isUpdating ||
    isAddingManual ||
    isRemovingManual ||
    isPreviewing;

  const renderDiscoveredRows = (items: CustomProviderDiscoveredModel[]) =>
    items.length === 0 ? null : (
      <ul className="flex flex-col gap-1">
        {items.map((m) => (
          <li
            key={`${m.model_id}-${m.model_type}`}
            className="flex items-center justify-between rounded-md border border-muted px-2 py-1 text-sm"
            data-testid={`custom-provider-model-${m.model_id}`}
          >
            <span className="truncate">{m.model_id}</span>
            {!isEdit ? (
              <Switch
                checked={discovered.some(
                  (d) =>
                    d.model_id === m.model_id && d.model_type === m.model_type,
                )}
                onCheckedChange={() =>
                  toggleDiscovered(m.model_id, m.model_type)
                }
                aria-label={t("customProviders.removeFromSelection")}
                data-testid={`custom-provider-toggle-${m.model_type}-${m.model_id}`}
              />
            ) : (
              <span className="text-xs text-muted-foreground">
                {m.model_type}
              </span>
            )}
          </li>
        ))}
      </ul>
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {t(
              isEdit
                ? "customProviders.editTitle"
                : "customProviders.createTitle",
            )}
          </DialogTitle>
          <DialogDescription>
            {t("customProviders.modalDescription")}
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto py-2">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="custom-provider-id" className="text-sm font-medium">
              {t("customProviders.providerIdLabel")}
            </label>
            <Input
              id="custom-provider-id"
              value={providerId}
              onChange={(e) => setProviderId(e.target.value)}
              disabled={isEdit}
              placeholder={t("customProviders.providerIdPlaceholder")}
              data-testid="custom-provider-id-input"
            />
            {isEdit && (
              <p className="text-xs text-muted-foreground">
                {t("customProviders.providerIdImmutable")}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="custom-provider-name"
              className="text-sm font-medium"
            >
              {t("customProviders.displayNameLabel")}
            </label>
            <Input
              id="custom-provider-name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder={t("customProviders.displayNamePlaceholder")}
              data-testid="custom-provider-name-input"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="custom-provider-url"
              className="text-sm font-medium"
            >
              {t("customProviders.baseUrlLabel")}
            </label>
            <Input
              id="custom-provider-url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.example.com/v1"
              data-testid="custom-provider-url-input"
            />
            {baseUrl.length > 0 && !baseUrl.trim().endsWith("/v1") && (
              <p className="text-xs text-muted-foreground">
                {t("customProviders.baseUrlV1Hint")}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="custom-provider-key"
              className="text-sm font-medium"
            >
              {t("customProviders.apiKeyLabel")}
            </label>
            <Input
              id="custom-provider-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                isEdit && provider?.has_api_key
                  ? t("customProviders.apiKeyMaskedPlaceholder")
                  : t("customProviders.apiKeyPlaceholder")
              }
              autoComplete="new-password"
              data-testid="custom-provider-key-input"
            />
          </div>

          {!isEdit && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">
                  {t("customProviders.discoveredModels")}
                </span>
                <Button
                  size="md"
                  variant="outline"
                  onClick={handlePreview}
                  disabled={!canPreview || pending}
                  data-testid="custom-provider-preview-button"
                >
                  <ForwardedIconComponent
                    name="RefreshCw"
                    className={cn(
                      "mr-1 h-4 w-4",
                      isPreviewing && "animate-spin",
                    )}
                  />
                  {t("customProviders.getModels")}
                </Button>
              </div>
              {preview &&
                (preview.error ? (
                  <p
                    className="text-sm text-destructive"
                    data-testid="custom-provider-preview-error"
                  >
                    {preview.error}
                  </p>
                ) : (
                  <div
                    className="flex flex-col gap-2"
                    data-testid="custom-provider-preview-results"
                  >
                    {(["llm", "embeddings"] as const).map((type) => (
                      <div key={type} className="flex flex-col gap-1">
                        <span className="text-xs font-medium text-muted-foreground">
                          {t(
                            `modelProviders.${type === "llm" ? "languageModels" : "embeddingModels"}`,
                          )}
                        </span>
                        {renderDiscoveredRows(
                          preview.models[type].map(
                            (id): CustomProviderDiscoveredModel => ({
                              model_id: id,
                              model_type: type,
                            }),
                          ),
                        )}
                      </div>
                    ))}
                  </div>
                ))}
            </div>
          )}

          {isEdit && discovered.length > 0 && (
            <div className="flex flex-col gap-2">
              <span className="text-sm font-medium">
                {t("customProviders.discoveredModels")}
              </span>
              {renderDiscoveredRows(discovered)}
              <p className="text-xs text-muted-foreground">
                {t("customProviders.discoveredHint")}
              </p>
            </div>
          )}

          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">
              {t("customProviders.manualModels")}
            </span>
            <div className="flex gap-2">
              <Input
                value={manualModelId}
                onChange={(e) => setManualModelId(e.target.value)}
                placeholder={t("customProviders.manualModelPlaceholder")}
                data-testid="custom-provider-manual-model-input"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void handleAddManual();
                  }
                }}
              />
              <Button
                size="md"
                variant="outline"
                onClick={() => void handleAddManual()}
                disabled={manualModelId.trim().length === 0 || pending}
                data-testid="custom-provider-add-model-button"
              >
                {t("customProviders.addButton")}
              </Button>
            </div>
            {manual.length === 0 && (
              <p className="text-xs text-muted-foreground">
                {t("customProviders.manualHint")}
              </p>
            )}
            {manual.length > 0 && (
              <ul className="flex flex-col gap-1">
                {manual.map((m) => (
                  <li
                    key={m.model_id}
                    className="flex items-center justify-between rounded-md border border-muted px-2 py-1 text-sm"
                    data-testid={`custom-provider-manual-model-${m.model_id}`}
                  >
                    <span className="truncate">{m.model_id}</span>
                    <Button
                      size="iconSm"
                      variant="ghost"
                      onClick={() => void handleRemoveManual(m.model_id)}
                      aria-label={t("customProviders.removeButton")}
                      data-testid={`custom-provider-remove-model-${m.model_id}`}
                    >
                      <ForwardedIconComponent name="X" className="h-4 w-4" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {error && (
            <p
              className="text-sm text-destructive"
              data-testid="custom-provider-modal-error"
            >
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("customProviders.cancelButton")}
          </Button>
          <Button
            onClick={() => void handleSave()}
            disabled={!canSave || pending}
            data-testid="custom-provider-save-button"
          >
            {t("customProviders.saveButton")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
