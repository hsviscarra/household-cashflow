import { useId, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import { type CategoryGroup } from "../api";
import { type PickEntry, pickEntries, searchEntries, type Mode } from "./categoryPick";
import { CreatePanel } from "./CreatePanel";

export { fold, type PickEntry, pickEntries, searchEntries } from "./categoryPick";

const MOST_USED = 5;

type Item =
  | { kind: "entry"; entry: PickEntry; section?: string; flat?: boolean }
  | { kind: "create-sub" }
  | { kind: "create-group" };

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
          className="field"
          // Inline: .field is plain CSS and outranks Tailwind's padding utilities (v4 layers), so
          // the color dot and the arrow need room set here.
          style={{ paddingLeft: selected && !open ? "2rem" : undefined, paddingRight: "2.25rem" }}
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
