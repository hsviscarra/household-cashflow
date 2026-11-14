import { type Mode, type PickEntry, entryOf, KIND_LABEL } from "./categoryPick";
import { type CategoryGroup, type CategoryKind, createCategory } from "../api";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { useState, type KeyboardEvent } from "react";

/** "Create a subcategory" (the usual way) or, deliberately one step further, "Create a group". */
export function CreatePanel(props: {
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
