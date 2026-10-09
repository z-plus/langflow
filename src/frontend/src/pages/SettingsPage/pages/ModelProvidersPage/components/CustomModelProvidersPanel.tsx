import { useState } from "react";
import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import {
  type CustomModelProvider,
  useGetCustomModelProviders,
} from "@/controllers/API/queries/custom-model-providers/use-custom-model-providers";
import CustomProviderCard from "./CustomProviderCard";
import CustomProviderDialog from "./CustomProviderDialog";

export default function CustomModelProvidersPanel() {
  const { t } = useTranslation();
  const providers = useGetCustomModelProviders();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<CustomModelProvider | null>(null);

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (provider: CustomModelProvider) => {
    setEditing(provider);
    setDialogOpen(true);
  };

  return (
    <section className="space-y-4" aria-labelledby="custom-providers-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="custom-providers-heading" className="font-semibold">
            {t("modelProviders.custom.title")}
          </h3>
          <p className="text-sm text-muted-foreground">
            {t("modelProviders.custom.description")}
          </p>
        </div>
        <Button type="button" size="md" onClick={openCreate}>
          <ForwardedIconComponent name="Plus" />
          {t("modelProviders.custom.addProvider")}
        </Button>
      </div>

      {providers.isLoading ? (
        <p
          className="rounded-lg border p-4 text-sm text-muted-foreground"
          role="status"
        >
          {t("modelProviders.loadingProviders")}
        </p>
      ) : providers.isError ? (
        <div
          className="rounded-lg border border-destructive/30 bg-destructive/5 p-4"
          role="alert"
        >
          <p className="text-sm text-destructive">
            {t("modelProviders.custom.errorLoadProviders")}
          </p>
          <Button
            className="mt-3"
            size="sm"
            variant="outline"
            onClick={() => providers.refetch()}
          >
            {t("modelProviders.custom.retry")}
          </Button>
        </div>
      ) : providers.data?.length ? (
        <div className="grid gap-3 xl:grid-cols-2">
          {providers.data.map((provider) => (
            <CustomProviderCard
              provider={provider}
              onEdit={openEdit}
              key={provider.id}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed px-6 py-8 text-center">
          <ForwardedIconComponent
            name="PlugZap"
            className="mx-auto h-6 w-6 text-muted-foreground"
          />
          <p className="mt-2 text-sm font-medium">
            {t("modelProviders.custom.emptyTitle")}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("modelProviders.custom.emptyDescription")}
          </p>
        </div>
      )}

      <CustomProviderDialog
        open={dialogOpen}
        provider={editing}
        onOpenChange={setDialogOpen}
      />
    </section>
  );
}
