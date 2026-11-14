import { localToday } from "../../money";
import { type ForecastChange, type Projection, fetchAccounts } from "../../api";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { signedMoney, day, minus } from "./shared";

export const ONCE_DEFAULT = () => localToday();

/** What if (ADR-033): changes added on top, compared with the forecast without them. */
export function WhatIfs({
  changes,
  setChanges,
  p,
}: {
  changes: ForecastChange[];
  setChanges: (c: ForecastChange[]) => void;
  p: Projection;
}) {
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });
  const banks = (accounts.data ?? []).filter((a) => a.kind !== "credit_card" && a.is_active);
  const [kind, setKind] = useState<"move" | "monthly" | "once">("move");
  const [amount, setAmount] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [name, setName] = useState("");
  const [onDay, setOnDay] = useState("1");
  const [onDate, setOnDate] = useState(ONCE_DEFAULT());
  const [direction, setDirection] = useState<"out" | "in">("out");
  const nameOf = (id: string) => banks.find((a) => String(a.account_id) === id)?.name ?? "";
  const add = () => {
    const v = Math.abs(Number(amount));
    if (!v) return;
    if (kind === "move") {
      if (!from || !to || from === to) return;
      const label = `Move ${nameOf(from)} → ${nameOf(to)}`;
      setChanges([
        ...changes,
        {
          name: label,
          amount: String(-v),
          every: "month",
          day: Number(onDay) || 1,
          account_id: Number(from),
        },
        { name: label, amount: String(v), every: "month", day: Number(onDay) || 1, account_id: Number(to) },
      ]);
    } else {
      const signedV = direction === "in" ? v : -v;
      setChanges([
        ...changes,
        {
          name: name.trim() || (kind === "once" ? "One-off" : "Each month"),
          amount: String(signedV),
          every: kind === "once" ? "once" : "month",
          day: Number(onDay) || 1,
          on: kind === "once" ? onDate : null,
          account_id: from ? Number(from) : null,
        },
      ]);
    }
    setAmount("");
    setName("");
  };
  const b = p.base;
  return (
    <section className="card" aria-labelledby="whatif">
      <h2 id="whatif" className="font-display text-xl font-bold">
        What if…
      </h2>
      <div role="group" aria-label="Kind of change" className="mt-3 flex flex-wrap gap-2 text-sm">
        {(
          [
            ["move", "Move money each month"],
            ["monthly", "Something each month"],
            ["once", "A one-off"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            aria-pressed={kind === k}
            className={`rounded-full border px-3 py-1.5 font-semibold ${kind === k ? "border-primary bg-info-bg" : "border-line"}`}
            onClick={() => setKind(k)}
          >
            {label}
          </button>
        ))}
      </div>
      <form
        className="mt-3 grid gap-2 sm:grid-cols-2"
        aria-label="Add a what-if"
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
      >
        {kind !== "move" && (
          <>
            <label>
              <span className="label">Name</span>
              <input
                className="field"
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              <span className="label">Money</span>
              <select
                className="field"
                value={direction}
                onChange={(e) => setDirection(e.target.value as "in" | "out")}
              >
                <option value="out">going out</option>
                <option value="in">coming in</option>
              </select>
            </label>
          </>
        )}
        <label>
          <span className="label">Amount</span>
          <input
            className="field num"
            inputMode="decimal"
            required
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </label>
        {kind === "once" ? (
          <label>
            <span className="label">On</span>
            <input type="date" className="field" value={onDate} onChange={(e) => setOnDate(e.target.value)} />
          </label>
        ) : (
          <label>
            <span className="label">On day</span>
            <input
              className="field num"
              type="number"
              min={1}
              max={31}
              value={onDay}
              onChange={(e) => setOnDay(e.target.value)}
            />
          </label>
        )}
        <label>
          <span className="label">{kind === "move" ? "From" : "Account (optional)"}</span>
          <select
            className="field"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            required={kind === "move"}
          >
            <option value="">{kind === "move" ? "Choose" : "Any"}</option>
            {banks.map((a) => (
              <option key={a.account_id} value={a.account_id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        {kind === "move" && (
          <label>
            <span className="label">To</span>
            <select className="field" value={to} onChange={(e) => setTo(e.target.value)} required>
              <option value="">Choose</option>
              {banks.map((a) => (
                <option key={a.account_id} value={a.account_id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="sm:col-span-2">
          <button type="submit" className="btn btn-secondary">
            Add to the forecast
          </button>
        </div>
      </form>
      {changes.length > 0 && (
        <>
          <ul className="mt-3 divide-y divide-line text-sm" aria-label="What-ifs added">
            {changes.map((c, i) => (
              <li key={i} className="flex items-center justify-between gap-2 py-1.5">
                <span>
                  {c.name}: <span className="num">{signedMoney(c.amount)}</span>{" "}
                  {c.every === "once" ? `on ${day(c.on!)}` : `each month on the ${c.day}`}
                </span>
                <button
                  type="button"
                  className="text-sm text-primary underline"
                  onClick={() => setChanges(changes.filter((_, j) => j !== i))}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
          {b && (
            <p className="mt-3 rounded-xl bg-surface px-3 py-2 text-sm" aria-live="polite">
              With these: lowest cash{" "}
              <strong className="num">{p.lowest ? minus(p.lowest.balance) : "—"}</strong> (was{" "}
              <span className="num">{b.lowest ? minus(b.lowest.balance) : "—"}</span>), first day short{" "}
              <strong>{p.first_short ? day(p.first_short) : "none"}</strong> (was{" "}
              {b.first_short ? day(b.first_short) : "none"}), cash at the end{" "}
              <strong className="num">{minus(String(p.end_cash ?? 0))}</strong> (was{" "}
              <span className="num">{minus(b.end_cash)}</span>).
            </p>
          )}
        </>
      )}
    </section>
  );
}
