import { type CategoryKind, type CategoryGroup, type Category } from "../api";

/** One choosable category: a group or a subcategory, with what the picker searches and shows. */
export type PickEntry = {
  id: number;
  name: string;
  path: string; // "Group / Sub" like the API paths, or "Group"
  groupId: number;
  isGroup: boolean;
  description: string;
  used: number; // loaded lines, then rules, decide "most used"
  color: string;
};

export const KIND_LABEL: Record<CategoryKind, string> = {
  expense: "Spending",
  income: "Income",
  savings: "Savings",
  debt: "Debt payments",
  transfer: "Transfers",
};

/** Lower case without accents, so "cafe" finds "Cafés" and "alicuota" finds "Alícuota". */
export function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/** Every active group and subcategory, in the Settings order (the selected one even if archived). */
export function pickEntries(groups: CategoryGroup[], keep?: number | ""): PickEntry[] {
  const out: PickEntry[] = [];
  const add = (c: Category, g: CategoryGroup) => {
    if (!c.is_active && c.category_id !== keep) return;
    const isGroup = c.category_id === g.category_id;
    out.push({
      id: c.category_id,
      name: c.name,
      path: isGroup ? g.name : `${g.name} / ${c.name}`,
      groupId: g.category_id,
      isGroup,
      description: c.description ?? "",
      used: (c.lines ?? 0) * 1000 + (c.rules ?? 0),
      color: g.color ?? "var(--color-muted)",
    });
  };
  for (const g of groups) {
    add(g, g);
    for (const c of g.children) add(c, g);
  }
  return out;
}

/** Entries matching every word of the query, best first: name starts with it, then the path
 * has it, then only the description does. */
export function searchEntries(entries: PickEntry[], query: string): PickEntry[] {
  const q = fold(query.trim());
  if (!q) return entries;
  const words = q.split(/\s+/);
  const scored: { e: PickEntry; score: number; order: number }[] = [];
  entries.forEach((e, order) => {
    const name = fold(e.name);
    const path = fold(e.path);
    const all = `${path} ${fold(e.description)}`;
    if (!words.every((w) => all.includes(w))) return;
    const score = name.startsWith(q)
      ? 0
      : path.includes(q)
        ? 1
        : words.every((w) => path.includes(w))
          ? 2
          : 3;
    scored.push({ e, score, order });
  });
  return scored.sort((a, b) => a.score - b.score || a.order - b.order).map((s) => s.e);
}

export type Mode = "list" | "sub" | "group";

export function entryOf(
  c: Category,
  groupName: string,
  groupId: number,
  color: string | null,
  isGroup = false,
): PickEntry {
  return {
    id: c.category_id,
    name: c.name,
    path: isGroup ? c.name : `${groupName} / ${c.name}`,
    groupId,
    isGroup,
    description: c.description ?? "",
    used: 0,
    color: color ?? "var(--color-muted)",
  };
}
