import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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
import { getAxiosErrorMessage } from "@/controllers/API/helpers/get-axios-error-message";
import {
  type CustomModelProvider,
  useCreateCustomModelProvider,
  useUpdateCustomModelProvider,
} from "@/controllers/API/queries/custom-model-providers/use-custom-model-providers";

interface CustomProviderDialogProps {
  open: boolean;
  provider: CustomModelProvider | null;
  onOpenChange: (open: boolean) => void;
}

export default function CustomProviderDialog({
  open,
  provider,
  onOpenChange,
}: CustomProviderDialogProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState("");
  const createProvider = useCreateCustomModelProvider();
  const updateProvider = useUpdateCustomModelProvider(provider?.id ?? "");
  const isPending = createProvider.isPending || updateProvider.isPending;

  useEffect(() => {
    if (!open) return;
    setName(provider?.name ?? "");
    setBaseUrl(provider?.base_url ?? "");
    setApiKey("");
    setError("");
  }, [open, provider]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      if (provider) {
        await updateProvider.mutateAsync({
          name: name.trim(),
          base_url: baseUrl.trim(),
          ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        });
      } else {
        await createProvider.mutateAsync({
          name: name.trim(),
          base_url: baseUrl.trim(),
          api_key: apiKey.trim(),
        });
      }
      onOpenChange(false);
    } catch (caught) {
      setError(
        getAxiosErrorMessage(caught, t("modelProviders.custom.errorSave")),
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t(
              provider
                ? "modelProviders.custom.editTitle"
                : "modelProviders.custom.createTitle",
            )}
          </DialogTitle>
          <DialogDescription>
            {t("modelProviders.custom.dialogDescription")}
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={submit}>
          <div className="space-y-2">
            <Label htmlFor="custom-provider-name">
              {t("modelProviders.custom.name")}
            </Label>
            <Input
              id="custom-provider-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={200}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="custom-provider-url">
              {t("modelProviders.custom.baseUrl")}
            </Label>
            <Input
              id="custom-provider-url"
              type="url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder={t("modelProviders.custom.baseUrlPlaceholder")}
              required
              maxLength={2048}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="custom-provider-key">
              {t("modelProviders.custom.apiKey")}
            </Label>
            <Input
              id="custom-provider-key"
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={
                provider?.has_api_key
                  ? t("modelProviders.custom.keyUnchanged")
                  : undefined
              }
              required={!provider}
            />
            {provider?.has_api_key && (
              <p className="text-xs text-muted-foreground">
                {t("modelProviders.custom.keyMasked")}
              </p>
            )}
          </div>
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              {t("modelProviders.cancelButton")}
            </Button>
            <Button type="submit" loading={isPending} disabled={isPending}>
              {t("modelProviders.saveButton")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
