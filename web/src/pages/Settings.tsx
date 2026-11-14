import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { type Notify } from "./settings/shared";
import { BankSyncTab } from "./settings/BankSyncTab";
import { AccountsTab } from "./settings/AccountsTab";
import { CategoriesTab } from "./settings/CategoriesTab";
import { RulesTab } from "./settings/RulesTab";

export { amountRange, appliedNote, alsoNote } from "./settings/RulesTab";

export { usesText, usage } from "./settings/CategoryParts";

const TABS = [
  { id: "accounts", label: "Accounts" },
  { id: "categories", label: "Categories" },
  { id: "rules", label: "Merchant rules" },
  { id: "sync", label: "Bank sync" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function Settings() {
  const [params, setParams] = useSearchParams();
  const tab: TabId = TABS.some((t) => t.id === params.get("tab")) ? (params.get("tab") as TabId) : "accounts";
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const notify: Notify = (message, tone = "good") => setStatus({ message, tone });

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">Settings</h1>
      <p className="mt-2 text-lg text-muted">
        The accounts, categories and merchant rules every import uses.
      </p>

      <div role="tablist" aria-label="Settings sections" className="mt-6 flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            className={`btn ${tab === t.id ? "bg-ink text-ground" : "btn-secondary"}`}
            onClick={() => {
              setStatus(null);
              setParams({ tab: t.id });
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <p
        aria-live="polite"
        className={
          status
            ? `mt-4 rounded-2xl px-4 py-3 ${status.tone === "good" ? "bg-good-bg text-good-ink" : "bg-danger-bg text-danger-ink"}`
            : "sr-only"
        }
      >
        {status?.message ?? ""}
      </p>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="mt-6">
        {tab === "accounts" && <AccountsTab notify={notify} />}
        {tab === "categories" && <CategoriesTab notify={notify} />}
        {tab === "rules" && <RulesTab notify={notify} />}
        {tab === "sync" && <BankSyncTab notify={notify} />}
      </div>
    </section>
  );
}
