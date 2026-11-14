import { useQueryClient } from "@tanstack/react-query";

export type Notify = (message: string, tone?: "good" | "bad") => void;

export const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

export const REFRESH = ["people", "notes", "transactions", "networth", "status", "review", "transfers"];

export function useRefresh() {
  const qc = useQueryClient();
  return () => REFRESH.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}
