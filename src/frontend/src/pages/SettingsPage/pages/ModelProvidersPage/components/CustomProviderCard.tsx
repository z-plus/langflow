import { useState } from "react";
import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Badge } from "@/components/ui/badge";
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
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { getAxiosErrorMessage } from "@/controllers/API/helpers/get-axios-error-message";
import {
  type CustomModelProvider,
  useAddCustomProviderModel,
  useDeleteCustomModelProvider,
  useDeleteCustomProviderModel,
  useGetCustomProviderModels,
  useRefreshCustomProviderModels,
} from "@/controllers/API/queries/custom-model-providers/use-custom-model-providers";
import { useGetEnabledModels } from "@/controllers/API/queries/models/use-get-enabled-models";
import { useUpdateEnabledModels } from "@/controllers/API/queries/models/use-update-enabled-models";

interface CustomProviderCardProps {
  provider: CustomModelProvider;
  onEdit: (provider: CustomModelProvider) => void;
}

export default function CustomProviderCard({
  provider,
  onEdit,
}: CustomProviderCardProps) {
  const { t } = useTranslation();
  const [modelId, setModelId] = useState("");
  const [error, setError] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [pendingEnabledModels, setPendingEnabledModels] = useState<
    Record<string, boolean>
  >({});
  const models = useGetCustomProviderModels(provider.id);
  const refreshModels = useRefreshCustomProviderModels(provider.id);
  const addModel = useAddCustomProviderModel(provider.id);
  const removeModel = useDeleteCustomProviderModel(provider.id);
  const deleteProvider = useDeleteCustomModelProvider();
  const enabledModels = useGetEnabledModels({ purpose: "configure" });
  const updateEnabledModels = useUpdateEnabledModels();
  const providerIdentity = `custom-openai-compatible:${provider.id}`;

  const run = async (operation: () => Promise<unknown>) => {
    setError("");
    try {
      await operation();
      return true;
    } catch (caught) {
      setError(
        getAxiosErrorMessage(caught, t("modelProviders.custom.errorAction")),
      );
      return false;
    }
  };

  const submitModel = async (event: React.FormEvent) => {
    event.preventDefault();
    const value = modelId.trim();
    if (!value) return;
    if (await run(() => addModel.mutateAsync(value))) setModelId("");
  };

  const isModelEnabled = (modelId: string) =>
    pendingEnabledModels[modelId] ??
    enabledModels.data?.enabled_models?.[providerIdentity]?.[modelId] ??
    false;

  const toggleModel = async (modelId: string, enabled: boolean) => {
    setPendingEnabledModels((current) => ({ ...current, [modelId]: enabled }));
    const updated = await run(() =>
      updateEnabledModels.mutateAsync({
        updates: [
          {
            provider: providerIdentity,
            model_id: modelId,
            model_type: "llm",
            enabled,
          },
        ],
      }),
    );
    if (updated) await enabledModels.refetch();
    setPendingEnabledModels((current) => {
      const next = { ...current };
      delete next[modelId];
      return next;
    });
  };

  return (
    <article className="space-y-4" data-testid="custom-provider-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="truncate font-medium">{provider.name}</h4>
            <Badge
              size="tag"
              variant={provider.is_verified ? "successStatic" : "errorStatic"}
            >
              {t(
                provider.is_verified
                  ? "modelProviders.custom.verified"
                  : "modelProviders.custom.unverified",
              )}
            </Badge>
          </div>
          <p className="break-all text-xs text-muted-foreground">
            {provider.base_url}
          </p>
        </div>
        <div className="flex gap-1">
          <Button
            type="button"
            size="iconMd"
            variant="ghost"
            aria-label={t("modelProviders.custom.editProvider", {
              name: provider.name,
            })}
            onClick={() => onEdit(provider)}
          >
            <ForwardedIconComponent name="Pencil" />
          </Button>
          <Button
            type="button"
            size="iconMd"
            variant="ghost"
            aria-label={t("modelProviders.custom.refreshProvider", {
              name: provider.name,
            })}
            loading={refreshModels.isPending}
            onClick={() => run(() => refreshModels.mutateAsync())}
          >
            <ForwardedIconComponent name="RefreshCw" />
          </Button>
          <Button
            type="button"
            size="iconMd"
            variant="ghost"
            aria-label={t("modelProviders.custom.deleteProvider", {
              name: provider.name,
            })}
            onClick={() => setDeleteOpen(true)}
          >
            <ForwardedIconComponent name="Trash2" />
          </Button>
        </div>
      </div>

      {provider.verification_error && (
        <div
          className="mt-3 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm"
          role="status"
        >
          <p className="font-medium text-destructive">
            {t("modelProviders.custom.discoveryFailed")}
          </p>
          <p className="mt-1 break-words text-muted-foreground">
            {provider.verification_error}
          </p>
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h5 className="text-sm font-medium">
            {t("modelProviders.languageModels")}
          </h5>
          <span className="text-xs text-muted-foreground">
            {t("modelProviders.custom.modelCount", {
              count: models.data?.length ?? 0,
            })}
          </span>
        </div>
        {models.isLoading ? (
          <p className="text-sm text-muted-foreground" role="status">
            {t("common.loading")}
          </p>
        ) : models.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {t("modelProviders.custom.errorLoadModels")}
          </p>
        ) : models.data?.length ? (
          <ul className="divide-y rounded-md border">
            {models.data.map((model) => (
              <li
                className="flex items-center justify-between gap-2 px-3 py-2"
                key={model.id}
              >
                <span className="min-w-0 truncate text-sm">
                  {model.model_id}
                </span>
                <div className="flex items-center gap-2">
                  {model.manually_added && (
                    <Badge size="tag" variant="secondaryStatic">
                      {t("modelProviders.custom.manual")}
                    </Badge>
                  )}
                  {model.manually_added && (
                    <Button
                      type="button"
                      size="iconSm"
                      variant="ghost"
                      aria-label={t("modelProviders.custom.removeModel", {
                        name: model.model_id,
                      })}
                      loading={removeModel.isPending}
                      onClick={() =>
                        run(() => removeModel.mutateAsync(model.model_id))
                      }
                    >
                      <ForwardedIconComponent name="X" />
                    </Button>
                  )}
                  <Switch
                    checked={isModelEnabled(model.model_id)}
                    disabled={
                      !model.available ||
                      enabledModels.isLoading ||
                      updateEnabledModels.isPending
                    }
                    onCheckedChange={(checked) =>
                      void toggleModel(model.model_id, checked)
                    }
                    aria-label={t(
                      isModelEnabled(model.model_id)
                        ? "modelProvider.disableModel"
                        : "modelProvider.enableModel",
                      { modelName: model.model_id },
                    )}
                    data-testid={`custom-model-toggle-${model.id}`}
                    stopPropagation
                  />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            {t("modelProviders.custom.noModels")}
          </p>
        )}

        <form className="flex items-end gap-2" onSubmit={submitModel}>
          <div className="min-w-0 flex-1 space-y-2">
            <Label htmlFor={`custom-model-${provider.id}`}>
              {t("modelProviders.custom.manualModelId")}
            </Label>
            <Input
              id={`custom-model-${provider.id}`}
              value={modelId}
              onChange={(event) => setModelId(event.target.value)}
              maxLength={200}
            />
          </div>
          <Button
            type="submit"
            variant="outline"
            loading={addModel.isPending}
            disabled={!modelId.trim() || addModel.isPending}
          >
            {t("modelProviders.custom.addModel")}
          </Button>
        </form>
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
      </div>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("modelProviders.custom.deleteTitle")}</DialogTitle>
            <DialogDescription>
              {t("modelProviders.custom.deleteWarning", {
                name: provider.name,
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              {t("modelProviders.cancelButton")}
            </Button>
            <Button
              variant="destructive"
              loading={deleteProvider.isPending}
              onClick={async () => {
                if (await run(() => deleteProvider.mutateAsync(provider.id))) {
                  setDeleteOpen(false);
                }
              }}
            >
              {t("modelProviders.custom.confirmDelete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </article>
  );
}
