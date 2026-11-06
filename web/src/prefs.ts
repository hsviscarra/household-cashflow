// Each signed-in person's own settings (ADR-026), saved on the server so they follow them from the
// laptop to the phone: the Both/Hernan/Lauren switch, row size, table columns and saved views.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchSettings, putSetting, type Settings } from "./api";

export type Person = "Both" | "Hernan" | "Lauren";
export const PEOPLE: Person[] = ["Both", "Hernan", "Lauren"];
export type Density = "comfortable" | "compact";
export type SavedView = { id: string; name: string; path: string; search: string; person: Person };

const KEY = ["settings"];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function useSettings() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: KEY, queryFn: fetchSettings, staleTime: Infinity, retry: false });
  const settings = asRecord(q.data?.settings);
  const save = useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) => putSetting(key, value),
    onError: () => qc.invalidateQueries({ queryKey: KEY }),
  });
  // Show the change at once (before the next click reads it); a failed save reloads what's stored.
  const set = (key: string, value: unknown) => {
    qc.setQueryData<Settings>(KEY, (old) => ({
      user: old?.user ?? "",
      settings: { ...asRecord(old?.settings), [key]: value },
    }));
    save.mutate({ key, value });
  };
  // Ready once the settings came back (or failed): pages wait for it so they load once, filtered.
  const ready = q.isSuccess || q.isError;
  return { settings, ready, set };
}

/** The Both/Hernan/Lauren switch. */
export function usePerson(): [Person, (p: Person) => void, boolean] {
  const { settings, set, ready } = useSettings();
  const value = settings.person;
  const person = PEOPLE.includes(value as Person) ? (value as Person) : "Both";
  return [person, (p) => set("person", p), ready];
}

/** The API's person filter: nothing for both of you. */
export const personParam = (p: Person) => (p === "Both" ? undefined : p);

export function useDensity(): [Density, (d: Density) => void] {
  const { settings, set } = useSettings();
  return [settings.density === "compact" ? "compact" : "comfortable", (d) => set("density", d)];
}

/** Which optional columns of a table are shown; every column when nothing is saved. */
export function useColumns(
  table: string,
  all: string[],
  defaults: string[] = all,
): [string[], (cols: string[]) => void] {
  const { settings, set } = useSettings();
  const saved = asRecord(settings[`table:${table}`]).columns;
  const shown = all.filter((c) => (Array.isArray(saved) ? saved : defaults).includes(c));
  return [shown, (cols) => set(`table:${table}`, { columns: all.filter((c) => cols.includes(c)) })];
}

export function useSavedViews() {
  const { settings, set } = useSettings();
  const raw = Array.isArray(settings.views) ? (settings.views as unknown[]) : [];
  const views = raw.filter(
    (v): v is SavedView =>
      !!v &&
      typeof v === "object" &&
      typeof (v as SavedView).name === "string" &&
      typeof (v as SavedView).path === "string",
  );
  return {
    views,
    add: (v: Omit<SavedView, "id">) =>
      set("views", [...views.filter((x) => x.name !== v.name), { ...v, id: `${Date.now()}` }]),
    remove: (id: string) =>
      set(
        "views",
        views.filter((v) => v.id !== id),
      ),
  };
}
