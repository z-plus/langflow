import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ForwardedIconComponent } from "@/components/common/genericIconComponent";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useDeleteCustomProvider,
  useGetCustomProviders,
  usePostCustomProviderRefresh,
} from "@/controllers/API/queries/custom-providers";
import type { CustomProvider } from "@/controllers/API/queries/custom-providers/types";
import DeleteConfirmationModal from "@/modals/deleteConfirmationModal";
import { cn } from "@/utils/utils";
import CustomProviderModal from "./CustomProviderModal";

const statusMeta: Record<
  CustomProvider["validation_status"],
  { dotClass: string; labelKey: string; detailKey?: string }
> = {
  draft: {
    dotClass: "bg-muted-foreground",
    labelKey: "customProviders.statusDraft",
  },
  valid: {
    dotClass: "bg-status-green",
    labelKey: "customProviders.statusValid",
  },
  invalid: {
    dotClass: "bg-destructive",
    labelKey: "customProviders.statusInvalid",
  },
};

const formatDate = (value?: string | null): string => {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : new Intl.DateTimeFormat().format(d);
};

function ValidationBadge({ provider }: { provider: CustomProvider }) {
  const { t } = useTranslation();
  const meta = statusMeta[provider.validation_status] ?? statusMeta.draft;
  return (
    <span
      title={
        provider.validation_status === "invalid"
          ? (provider.validation_error ?? undefined)
          : undefined
      }
      className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
      data-testid={`validation-badge-${provider.provider_id}`}
    >
      <span className={cn("h-2 w-2 rounded-full", meta.dotClass)} />
      {t(meta.labelKey)}
    </span>
  );
}

export default function CustomProvidersSection() {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<CustomProvider | null>(null);
  const [deleting, setDeleting] = useState<CustomProvider | null>(null);

  const { data: providers = [], isLoading } = useGetCustomProviders({
    search: search || undefined,
  });
  const { mutate: refresh } = usePostCustomProviderRefresh();
  const { mutate: remove } = useDeleteCustomProvider();

  const modelCount = (p: CustomProvider) =>
    p.discovered_models.length + p.manual_models.length;

  return (
    <section
      className="flex w-full flex-col gap-3"
      data-testid="custom-providers-section"
    >
      <div className="flex w-full items-center justify-between gap-4">
        <div className="flex flex-col">
          <h3 className="flex items-center text-base font-semibold tracking-tight">
            {t("customProviders.sectionTitle")}
            <ForwardedIconComponent
              name="Plug"
              className="ml-2 h-4 w-4 text-primary"
            />
          </h3>
          <p className="text-sm text-muted-foreground">
            {t("customProviders.sectionDescription")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Input
            icon="Search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("customProviders.search")}
            aria-label={t("customProviders.search")}
            className="w-56"
            data-testid="custom-providers-search"
          />
          <Button
            data-testid="new-custom-provider-button"
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
          >
            <ForwardedIconComponent name="Plus" className="mr-1 h-4 w-4" />
            {t("customProviders.newButton")}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">
          {t("modelProviders.loadingProviders")}
        </div>
      ) : providers.length === 0 ? (
        <div
          className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground"
          data-testid="custom-providers-empty"
        >
          {t("customProviders.emptyState")}
        </div>
      ) : (
        <ul className="flex flex-col gap-2" data-testid="custom-providers-list">
          {providers.map((provider) => (
            <li
              key={provider.id}
              className="flex items-center justify-between gap-4 rounded-lg border p-3"
              data-testid={`custom-provider-card-${provider.provider_id}`}
            >
              <div className="flex min-w-0 items-start gap-3">
                <ForwardedIconComponent
                  name={
                    (provider.validation_status === "invalid"
                      ? "AlertTriangle"
                      : "Plug") as never
                  }
                  className={cn(
                    "mt-0.5 h-5 w-5 flex-shrink-0",
                    provider.validation_status === "invalid"
                      ? "text-destructive"
                      : "text-primary",
                  )}
                />
                <div className="flex min-w-0 flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">
                      {provider.display_name}
                    </span>
                    <ValidationBadge provider={provider} />
                    {provider.has_api_key && (
                      <Badge variant="secondary" size="sq" className="text-xs">
                        {t("customProviders.keyConfigured")}
                      </Badge>
                    )}
                  </div>
                  <span className="truncate text-xs text-muted-foreground">
                    {provider.provider_id}
                  </span>
                  <span className="truncate text-xs text-muted-foreground">
                    {provider.base_url}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {t("customProviders.modelCount", {
                      count: modelCount(provider),
                    })}{" "}
                    ·{" "}
                    {t("customProviders.updatedAt", {
                      date: formatDate(provider.updated_at),
                    })}
                  </span>
                </div>
              </div>
              <div className="flex flex-shrink-0 items-center gap-1">
                <Button
                  size="iconMd"
                  variant="ghost"
                  onClick={() => {
                    refresh({ provider_id: provider.provider_id });
                  }}
                  title={t("customProviders.refreshButton")}
                  aria-label={t("customProviders.refreshButton")}
                  data-testid={`custom-provider-refresh-${provider.provider_id}`}
                >
                  <ForwardedIconComponent
                    name="RefreshCw"
                    className="h-4 w-4"
                  />
                </Button>
                <Button
                  size="iconMd"
                  variant="ghost"
                  onClick={() => {
                    setEditing(provider);
                    setModalOpen(true);
                  }}
                  title={t("customProviders.editButton")}
                  aria-label={t("customProviders.editButton")}
                  data-testid={`custom-provider-edit-${provider.provider_id}`}
                >
                  <ForwardedIconComponent name="Pencil" className="h-4 w-4" />
                </Button>
                <DeleteConfirmationModal
                  open={deleting?.id === provider.id}
                  setOpen={(open) => setDeleting(open ? provider : null)}
                  description={t("customProviders.deleteConfirmDescription")}
                  note={t("customProviders.deleteConfirmNote")}
                  onConfirm={() => {
                    remove({ provider_id: provider.provider_id });
                  }}
                >
                  <Button
                    size="iconMd"
                    variant="ghost"
                    title={t("customProviders.deleteButton")}
                    aria-label={t("customProviders.deleteButton")}
                    data-testid={`custom-provider-delete-${provider.provider_id}`}
                  >
                    <ForwardedIconComponent
                      name="Trash2"
                      className="h-4 w-4 text-destructive"
                    />
                  </Button>
                </DeleteConfirmationModal>
              </div>
            </li>
          ))}
        </ul>
      )}

      <CustomProviderModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        provider={editing}
      />
    </section>
  );
}
