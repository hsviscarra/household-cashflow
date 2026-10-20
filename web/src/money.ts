// Display helpers. Amounts stay decimal strings from the API; numbers are only for drawing.
const two = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LONG = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export const num = (v: string | number | null | undefined) => (v == null ? 0 : Number(v));

/** 12,345.67 — tables and tiles (USD, no symbol). */
export const money = (v: string | number | null | undefined) => two.format(num(v));

/** +12,345.67 for income-style figures. */
export const signed = (v: string | number) => (num(v) > 0 ? "+" : "") + money(v);

/** 12K — axis ticks. */
export const short = (v: number) => compact.format(v);

export const pct = (v: string | number | null | undefined) =>
  v == null ? "—" : `${Math.round(num(v) * 100)}%`;

/** "2026-01-01" -> month index and year without timezone surprises. */
export const parts = (iso: string) => ({ year: Number(iso.slice(0, 4)), month: Number(iso.slice(5, 7)) });
export const monthShort = (iso: string) => MONTHS[parts(iso).month - 1];
export const monthLong = (iso: string) => `${LONG[parts(iso).month - 1]} ${parts(iso).year}`;
export const monthName = (m: number) => LONG[m - 1];

/** Money out without a sign, money back with + (docs/design-system.md). */
export const showAmount = (v: string | number) => (num(v) > 0 ? signed(v) : money(-num(v)));
