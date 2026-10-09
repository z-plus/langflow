import { useState } from "react";
import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import type { CustomModelProvider } from "@/controllers/API/queries/custom-model-providers/use-custom-model-providers";
import ModelProvidersContent from "@/modals/modelProviderModal/components/ModelProvidersContent";
import CustomProviderDialog from "./components/CustomProviderDialog";

export default function ModelProvidersPage() {
  const { t } = useTranslation();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingProvider, setEditingProvider] =
    useState<CustomModelProvider | null>(null);

  const openCreateDialog = () => {
    setEditingProvider(null);
    setDialogOpen(true);
  };

  const openEditDialog = (provider: CustomModelProvider) => {
    setEditingProvider(provider);
    setDialogOpen(true);
  };
  return (
    <div className="flex w-full flex-col gap-6">
      <div className="flex w-full items-start justify-between gap-6">
        <div className="flex flex-col">
          <h2
            className="flex items-center text-lg font-semibold tracking-tight"
            data-testid="settings_menu_header"
          >
            {t("modelProviders.pageTitle")}
            <ForwardedIconComponent
              name="BrainCircuit"
              className="ml-2 h-5 w-5 text-primary"
            />
          </h2>
          <p className="text-sm text-muted-foreground">
            {t("modelProviders.pageDescription")}
          </p>
        </div>
        <Button type="button" size="md" onClick={openCreateDialog}>
          <ForwardedIconComponent name="Plus" />
          {t("modelProviders.custom.addProvider")}
        </Button>
      </div>
      <div className="flex w-full h-[calc(100vh-305px)] border rounded-lg overflow-hidden">
        <ModelProvidersContent
          modelType="all"
          onEditCustomProvider={openEditDialog}
        />
      </div>
      <CustomProviderDialog
        open={dialogOpen}
        provider={editingProvider}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}
