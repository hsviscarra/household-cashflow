import { num, money, monthLong } from "../../money";
import { type Projection } from "../../api";

export const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export const signedMoney = (v: string | number) =>
  `${num(v) < 0 ? "−" : num(v) > 0 ? "+" : ""}${money(Math.abs(num(v)))}`;

/** "Next 3 months: −5,016.63; lowest cash −2,231.66 on Jan 20, before Hernan (Salaries) on Jan 21." */
export function projectionHeadline(p: Projection): string {
  const net = p.months.reduce((sum, m) => sum + num(m.net), 0);
  let text = `Next ${p.months.length} ${p.months.length === 1 ? "month" : "months"}: ${signedMoney(net)}`;
  if (p.lowest) {
    text += `; lowest cash ${signedMoney(p.lowest.balance).replace(/^\+/, "")} on ${day(p.lowest.day)}`;
    if (p.next_payday) text += `, before ${p.next_payday.name} on ${day(p.next_payday.day)}`;
  }
  return `${text}.`;
}

/** "In 8 of 10 cases cash ends January between 1,200.00 and 4,800.00. About a 15% chance it
 * goes under zero on the way." Empty without enough history for a range (ADR-096). */
export function rangeLine(p: Projection): string {
  const last = p.months[p.months.length - 1];
  if (!last || last.end_cash_low == null || last.end_cash_high == null) return "";
  const floor = num(p.floor ?? 0);
  const under = floor > 0 ? `your ${money(floor)} floor` : "zero";
  const chance = p.chance_under_floor == null ? null : Math.round(num(p.chance_under_floor) * 100);
  const risk =
    chance == null
      ? ""
      : chance === 0
        ? ` It stays over ${under} in every case tried.`
        : chance === 100
          ? ` It goes under ${under} on the way in every case tried.`
          : ` About a ${chance}% chance it goes under ${under} on the way.`;
  return `In 8 of 10 cases cash ends ${monthLong(last.month)} between ${minus(last.end_cash_low)} and ${minus(last.end_cash_high)}.${risk}`;
}

export const minus = (v: string) => (num(v) < 0 ? `−${money(Math.abs(num(v)))}` : money(v));
