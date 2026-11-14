import { type CategoryGroup } from "../../api";

// To do (ADR-047, ADR-058): everything that needs you, one section at a time. Each task carries
// its own action; a finished one leaves the list and a message confirms it at the bottom.

export type Notify = (text: string, tone?: "good" | "bad") => void;

export type Ctx = { groups: CategoryGroup[]; notify: Notify; finish: (key: string, text: string) => void };
