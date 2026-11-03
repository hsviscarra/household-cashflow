import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";

import { createCategory, type Category, type CategoryGroup, type CategoryKind } from "../api";

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

const KIND_LABEL: Record<CategoryKind, string> = {
  expense: "Spending",
  income: "Income",
  savings: "Savings & debt",
  transfer: "Transfers",
};
const MOST_USED = 5;

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

type Item =
  | { kind: "entry"; entry: PickEntry; section?: string; flat?: boolean }
  | { kind: "create-sub" }
  | { kind: "create-group" };

type Mode = "list" | "sub" | "group";

export default function CategoryPicker(props: {
  label: string;
  value: number | "";
  onChange: (id: number | "") => void;
  groups: CategoryGroup[];
  /** Hide the label visually (it stays for screen readers), e.g. inside a table cell. */
  hideLabel?: boolean;
  required?: boolean;
  /** Offer "Create …" when nothing fits (default on). */
  allowCreate?: boolean;
  placeholder?: string;
}) {
  const { value, onChange, groups } = props;
  const allowCreate = props.allowCreate ?? true;
  const base = useId();
  const listId = `${base}-list`;
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [mode, setMode] = useState<Mode>("list");
  // Created here and not yet in `groups` (the list refreshes a moment later).
  const [made, setMade] = useState<PickEntry[]>([]);
  const quiet = useRef(false); // focus back after creating, without reopening the list

  const entries = useMemo(() => {
    const known = pickEntries(groups, value);
    return [...known, ...made.filter((m) => !known.some((k) => k.id === m.id))];
  }, [groups, value, made]);
  const selected = entries.find((e) => e.id === value);

  const items: Item[] = useMemo(() => {
    const q = query.trim();
    if (q) {
      const found: Item[] = searchEntries(entries, q).map((entry) => ({ kind: "entry", entry }));
      if (!allowCreate) return found;
      return [...found, { kind: "create-sub" }, { kind: "create-group" }];
    }
    const top = [...entries]
      .filter((e) => e.used > 0)
      .sort((a, b) => b.used - a.used)
      .slice(0, MOST_USED);
    return [
      ...top.map((entry, i): Item => ({
        kind: "entry",
        entry,
        flat: true,
        section: i === 0 ? "Most used" : undefined,
      })),
      ...entries.map((entry, i): Item => ({
        kind: "entry",
        entry,
        section: i === 0 && top.length ? "All categories" : undefined,
      })),
      ...(allowCreate ? [{ kind: "create-group" } as Item] : []),
    ];
  }, [entries, query, allowCreate]);

  const close = () => {
    setOpen(false);
    setQuery("");
    setMode("list");
  };
  const pick = (id: number) => {
    onChange(id);
    close();
  };
  const choose = (item: Item | undefined) => {
    if (!item) return;
    if (item.kind === "entry") pick(item.entry.id);
    else setMode(item.kind === "create-sub" ? "sub" : "group");
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) setOpen(true);
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((a) => (items.length ? (a + step + items.length) % items.length : 0));
    } else if (e.key === "Enter" && open) {
      e.preventDefault(); // never submit the surrounding form from the picker
      choose(items[active]);
    } else if (e.key === "Escape" && open) {
      e.preventDefault();
      close();
    }
  };
  const optionId = (i: number) => `${base}-opt-${i}`;
  const best = items.find((i): i is Extract<Item, { kind: "entry" }> => i.kind === "entry")?.entry;

  return (
    <div
      ref={box}
      className="relative"
      onBlur={(e) => {
        if (!box.current?.contains(e.relatedTarget as Node | null)) close();
      }}
    >
      <label htmlFor={`${base}-input`} className={props.hideLabel ? "sr-only" : "label"}>
        {props.label}
      </label>
      <div className="relative">
        {selected && !open && (
          <span
            aria-hidden
            className="pointer-events-none absolute left-3 top-1/2 h-3 w-3 -translate-y-1/2 rounded-full"
            style={{ background: selected.color }}
          />
        )}
        <input
          ref={input}
          id={`${base}-input`}
          className={`field pr-9 ${selected && !open ? "pl-8" : ""}`}
          role="combobox"
          aria-expanded={open && mode === "list"}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-required={props.required}
          aria-activedescendant={open && mode === "list" && items.length ? optionId(active) : undefined}
          aria-describedby={selected?.description && !open ? `${base}-about` : undefined}
          autoComplete="off"
          placeholder={props.placeholder ?? "Search or choose a category"}
          value={open ? query : (selected?.path ?? "")}
          onFocus={() => {
            if (quiet.current) {
              quiet.current = false;
              return;
            }
            setOpen(true);
            setActive(0);
          }}
          onClick={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
            setMode("list");
            setOpen(true);
          }}
          onKeyDown={onKey}
        />
        <span
          aria-hidden
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted"
        >
          ▾
        </span>
      </div>
      {selected?.description && !open && (
        <p id={`${base}-about`} className="mt-1 text-xs text-muted">
          {selected.description}
        </p>
      )}

      {open && mode === "list" && (
        <ul
          id={listId}
          role="listbox"
          aria-label={props.label}
          className="absolute left-0 right-0 z-30 mt-1 max-h-80 overflow-auto rounded-2xl border border-line bg-ground py-1 shadow-lg"
        >
          {items.length === 0 && <li className="px-4 py-2 text-sm text-muted">No category matches.</li>}
          {items.map((item, i) => {
            const isActive = i === active;
            const common = {
              id: optionId(i),
              role: "option" as const,
              "aria-selected": isActive,
              onMouseDown: (e: MouseEvent) => e.preventDefault(), // keep focus in the input
              onMouseEnter: () => setActive(i),
              onClick: () => choose(item),
              className: `cursor-pointer px-4 py-2 ${isActive ? "bg-surface" : ""}`,
            };
            if (item.kind !== "entry") {
              return (
                <li key={item.kind} {...common} className={`${common.className} font-semibold text-primary`}>
                  {item.kind === "create-sub"
                    ? `+ Create “${query.trim()}” as a subcategory…`
                    : "No group fits? Create a group…"}
                </li>
              );
            }
            const e = item.entry;
            const flat = query.trim() !== "" || !!item.flat; // full path, no indent
            return [
              item.section && (
                <li
                  key={`${item.section}-head`}
                  role="presentation"
                  className="px-4 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-muted"
                >
                  {item.section}
                </li>
              ),
              <li key={`${i}-${e.id}`} {...common}>
                <span className={`flex items-center gap-2 ${!e.isGroup && !flat ? "pl-5" : ""}`}>
                  <span
                    aria-hidden
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: e.color }}
                  />
                  <span className={e.isGroup ? "font-semibold" : ""}>{flat ? e.path : e.name}</span>
                  {e.id === value && <span className="text-xs text-muted">· chosen</span>}
                </span>
                {e.description && (isActive || query.trim() !== "") && (
                  <span
                    className={`mt-0.5 block text-xs text-muted ${isActive ? "" : "line-clamp-1"} pl-[18px]`}
                  >
                    {e.description}
                  </span>
                )}
              </li>,
            ];
          })}
        </ul>
      )}

      {open && mode !== "list" && (
        <CreatePanel
          mode={mode}
          name={query.trim()}
          groups={groups}
          suggestGroup={best?.groupId}
          onBack={() => {
            setMode("list");
            input.current?.focus();
          }}
          onSwitch={setMode}
          onCreated={(entry) => {
            setMade((m) => [...m, entry]);
            pick(entry.id);
            quiet.current = true;
            input.current?.focus();
          }}
        />
      )}
    </div>
  );
}

/** "Create a subcategory" (the usual way) or, deliberately one step further, "Create a group". */
function CreatePanel(props: {
  mode: Exclude<Mode, "list">;
  name: string;
  groups: CategoryGroup[];
  suggestGroup?: number;
  onBack: () => void;
  onSwitch: (m: Mode) => void;
  onCreated: (e: PickEntry) => void;
}) {
  const qc = useQueryClient();
  const isSub = props.mode === "sub";
  const [name, setName] = useState(props.name);
  const [about, setAbout] = useState("");
  const [parent, setParent] = useState<number | "">(props.suggestGroup ?? "");
  const [groupName, setGroupName] = useState(props.name);
  const [kind, setKind] = useState<CategoryKind>("expense");
  const save = useMutation({
    mutationFn: async () => {
      const description = about.trim() || null;
      if (isSub) {
        const g = props.groups.find((x) => x.category_id === parent);
        if (!g) throw new Error("Choose the group it belongs to.");
        const c = await createCategory({ name: name.trim(), parent_id: g.category_id, description });
        return entryOf(c, g.name, g.category_id, g.color);
      }
      const g = await createCategory({
        name: groupName.trim(),
        kind,
        description: name.trim() ? null : description,
      });
      if (!name.trim()) return entryOf(g, g.name, g.category_id, g.color, true);
      const c = await createCategory({ name: name.trim(), parent_id: g.category_id, description });
      return entryOf(c, g.name, g.category_id, g.color);
    },
    onSuccess: (entry) => {
      qc.invalidateQueries({ queryKey: ["categories"] });
      props.onCreated(entry);
    },
  });
  const ready = isSub ? name.trim() !== "" && parent !== "" : groupName.trim() !== "";
  const submit = () => ready && !save.isPending && save.mutate();
  const enter = (e: KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault(); // no nested form: Enter creates
      submit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      props.onBack();
    }
  };

  return (
    <div
      role="group"
      aria-label={isSub ? "New subcategory" : "New group"}
      className="absolute left-0 right-0 z-30 mt-1 space-y-3 rounded-2xl border border-line bg-ground p-4 shadow-lg"
      onKeyDown={enter}
    >
      <p className="font-semibold">{isSub ? "New subcategory" : "New group"}</p>
      {!isSub && (
        <>
          <p className="text-sm text-muted">
            Groups shape every report, so add one only when none of the existing ones fits.
          </p>
          <label className="block">
            <span className="label">Group name</span>
            <input
              className="field"
              maxLength={100}
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="label">It is</span>
            <select className="field" value={kind} onChange={(e) => setKind(e.target.value as CategoryKind)}>
              {(Object.keys(KIND_LABEL) as CategoryKind[]).map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL[k]}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
      <label className="block">
        <span className="label">{isSub ? "Name" : "First subcategory (optional)"}</span>
        <input className="field" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      {isSub && (
        <label className="block">
          <span className="label">In the group</span>
          <select
            className="field"
            value={parent}
            onChange={(e) => setParent(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">Choose a group</option>
            {props.groups
              .filter((g) => g.is_active)
              .map((g) => (
                <option key={g.category_id} value={g.category_id}>
                  {g.name}
                </option>
              ))}
          </select>
        </label>
      )}
      <label className="block">
        <span className="label">What goes here (optional)</span>
        <input
          className="field"
          maxLength={400}
          placeholder="e.g. Food, treats and toys for the pets"
          value={about}
          onChange={(e) => setAbout(e.target.value)}
        />
      </label>
      {save.error && <p className="text-sm text-danger-ink">{(save.error as Error).message}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-primary"
          disabled={!ready || save.isPending}
          onClick={submit}
        >
          {save.isPending ? "Creating…" : "Create and use"}
        </button>
        <button type="button" className="btn btn-quiet" onClick={props.onBack}>
          Back to the list
        </button>
        {isSub && (
          <button type="button" className="btn btn-quiet" onClick={() => props.onSwitch("group")}>
            No group fits? Create a group…
          </button>
        )}
      </div>
    </div>
  );
}

function entryOf(
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
