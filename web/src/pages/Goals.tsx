// Saving goals (ADR-040): each goal's progress, what it needs each month to arrive on its date,
// and whether the planned monthly amount gets it there.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createGoal,
  deleteGoal,
  fetchGoals,
  updateGoal,
  type Goal,
  type GoalInput,
  type GoalPlace,
} from "../api";
import { money, num } from "../money";

const STATUS: Record<Goal["status"], { text: string; cls: string }> = {
  reached: { text: "Reached", cls: "bg-good-bg text-good-ink" },
  on_pace: { text: "On pace", cls: "bg-good-bg text-good-ink" },
  behind: { text: "Behind", cls: "bg-attention-bg text-attention-ink" },
  late: { text: "Date passed", cls: "bg-danger-bg text-danger-ink" },
  open: { text: "No date", cls: "bg-surface text-muted" },
};
const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", year: "numeric" });

/** One sentence on what the goal needs. */
export function paceLine(g: Goal): string {
  switch (g.status) {
    case "reached":
      return "Reached. Well done.";
    case "open":
      return `${money(g.left)} to go. Add a date to see what it needs each month.`;
    case "late":
      return `${money(g.left)} short and the date has passed: set a new date.`;
    case "on_pace":
      return `On pace: ${money(g.monthly_amount ?? 0)} a month reaches it by ${day(g.target_date!)}.`;
    case "behind": {
      const planned = num(g.monthly_amount);
      return planned
        ? `Put ${money(g.needed_monthly!)} a month (not ${money(planned)}) to reach it by ${day(g.target_date!)}.`
        : `Needs ${money(g.needed_monthly!)} a month to reach it by ${day(g.target_date!)}.`;
    }
  }
}

export default function GoalsPage() {
  const q = useQuery({ queryKey: ["goals"], queryFn: fetchGoals });
  const [adding, setAdding] = useState(false);
  const goals = q.data?.goals ?? [];
  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight">Goals</h1>
          <p className="mt-2 max-w-3xl text-lg text-muted">
            What you're saving for, where the money is, and what each goal needs a month to arrive on time.
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
          Add a goal
        </button>
      </div>
      {q.error && <p className="mt-4 text-danger-ink">{(q.error as Error).message}</p>}
      {adding && q.data && <GoalForm places={q.data.places} onDone={() => setAdding(false)} />}
      {q.data && !goals.length && !adding && (
        <p className="card mt-6">
          No goals yet. An emergency fund (six months of fixed costs), the house down payment or a trip are
          good first ones.
        </p>
      )}
      <ul className="mt-6 grid gap-4 lg:grid-cols-2" aria-label="Goals">
        {goals.map((g) => (
          <GoalCard key={g.goal_id} g={g} places={q.data!.places} />
        ))}
      </ul>
    </section>
  );
}

function GoalCard({ g, places }: { g: Goal; places: GoalPlace[] }) {
  const [editing, setEditing] = useState(false);
  const s = STATUS[g.status];
  const share = num(g.share) * 100;
  return (
    <li>
      <section className={`card ${g.is_active ? "" : "opacity-60"}`} aria-label={g.name}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="font-display text-xl font-bold">{g.name}</h2>
            <p className="text-sm text-muted">
              {g.place_name ? `In ${g.place_name}` : "Saved amount typed by hand"}
              {g.target_date && ` · by ${day(g.target_date)}`}
              {!g.is_active && " · paused"}
            </p>
          </div>
          <span className={`pill ${s.cls}`}>{s.text}</span>
        </div>
        <p className="num mt-3 font-display text-3xl font-bold tracking-tight">
          {money(g.current)}{" "}
          <span className="text-base font-medium text-muted">of {money(g.target_amount)}</span>
        </p>
        <div
          className="mt-2 h-3 rounded-full bg-surface"
          role="progressbar"
          aria-label={`${g.name}: saved`}
          aria-valuenow={Math.round(share)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={`h-3 rounded-full ${g.status === "behind" || g.status === "late" ? "bg-warn" : "bg-primary"}`}
            style={{ width: `${share}%` }}
          />
        </div>
        <p className="mt-2 text-sm">{paceLine(g)}</p>
        <button type="button" className="btn btn-quiet mt-2 h-9 px-3" onClick={() => setEditing(!editing)}>
          {editing ? "Close" : "Change"}
        </button>
        {editing && <GoalForm goal={g} places={places} onDone={() => setEditing(false)} />}
      </section>
    </li>
  );
}

function GoalForm({ goal, places, onDone }: { goal?: Goal; places: GoalPlace[]; onDone: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(goal?.name ?? "");
  const [target, setTarget] = useState(goal?.target_amount ?? "");
  const [date, setDate] = useState(goal?.target_date ?? "");
  const [place, setPlace] = useState(goal?.item_key ?? "");
  const [saved, setSaved] = useState(goal?.saved_amount ?? "");
  const [monthly, setMonthly] = useState(goal?.monthly_amount ?? "");
  const done = () => {
    void qc.invalidateQueries({ queryKey: ["goals"] });
    onDone();
  };
  const save = useMutation({
    mutationFn: () => {
      const body: GoalInput = {
        name: name.trim(),
        target_amount: String(num(target)),
        target_date: date || null,
        item_key: place || null,
        saved_amount: place ? null : saved ? String(num(saved)) : null,
        monthly_amount: monthly ? String(num(monthly)) : null,
      };
      return goal ? updateGoal(goal.goal_id, body) : createGoal(body);
    },
    onSuccess: done,
  });
  const pause = useMutation({
    mutationFn: () => updateGoal(goal!.goal_id, { is_active: !goal!.is_active }),
    onSuccess: done,
  });
  const remove = useMutation({ mutationFn: () => deleteGoal(goal!.goal_id), onSuccess: done });
  return (
    <form
      className={`grid gap-3 sm:grid-cols-2 ${goal ? "mt-3 border-t border-line pt-3" : "card mt-6"}`}
      aria-label={goal ? `Change ${goal.name}` : "New goal"}
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim() && num(target) > 0) save.mutate();
      }}
    >
      <label>
        <span className="label">Name</span>
        <input
          className="field"
          required
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        <span className="label">Target</span>
        <input
          className="field num"
          required
          inputMode="decimal"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        />
      </label>
      <label>
        <span className="label">By (optional)</span>
        <input className="field" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <label>
        <span className="label">Planned each month (optional)</span>
        <input
          className="field num"
          inputMode="decimal"
          value={monthly}
          onChange={(e) => setMonthly(e.target.value)}
        />
      </label>
      <label>
        <span className="label">Where the money is</span>
        <select className="field" value={place} onChange={(e) => setPlace(e.target.value)}>
          <option value="">Not in one place: I'll type the amount</option>
          {places.map((p) => (
            <option key={p.key} value={p.key}>
              {p.name}
              {p.value != null ? ` (${money(p.value)})` : ""}
            </option>
          ))}
        </select>
      </label>
      {!place && (
        <label>
          <span className="label">Saved so far</span>
          <input
            className="field num"
            inputMode="decimal"
            value={saved}
            onChange={(e) => setSaved(e.target.value)}
          />
        </label>
      )}
      <div className="flex flex-wrap gap-2 sm:col-span-2">
        <button type="submit" className="btn btn-primary" disabled={save.isPending}>
          {goal ? "Save" : "Add the goal"}
        </button>
        {!goal && (
          <button type="button" className="btn btn-quiet" onClick={onDone}>
            Cancel
          </button>
        )}
        {goal && (
          <>
            <button type="button" className="btn btn-secondary" onClick={() => pause.mutate()}>
              {goal.is_active ? "Pause" : "Resume"}
            </button>
            <button type="button" className="btn btn-quiet text-danger-ink" onClick={() => remove.mutate()}>
              Delete
            </button>
          </>
        )}
      </div>
      {save.error && <p className="text-sm text-danger-ink sm:col-span-2">{(save.error as Error).message}</p>}
    </form>
  );
}
