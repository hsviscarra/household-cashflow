import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchCategories, fetchPeople } from "../api";
import { type Notify } from "./people/shared";
import { NoteForm, Notes } from "./people/Notes";
import { People } from "./people/PersonForm";

/** People whose money passes through the household's accounts, and transfers told to the app
 * before their statement arrives (ADR-023). */
export default function PeoplePage() {
  const [status, setStatus] = useState<{ message: string; tone: "good" | "bad" } | null>(null);
  const notify: Notify = (message, tone = "good") => setStatus({ message, tone });
  const cats = useQuery({ queryKey: ["categories"], queryFn: fetchCategories });
  const peopleQ = useQuery({ queryKey: ["people"], queryFn: fetchPeople });

  return (
    <section>
      <h1 className="font-display text-4xl font-bold leading-tight">People & transfers</h1>
      <p className="mt-2 text-lg text-muted">
        Statements often say only “TRANSFERENCIA”. Tell the app who a transfer was for, and it names and
        categorizes the line when the statement is read.
      </p>
      <p
        aria-live="polite"
        className={
          status
            ? `mt-4 rounded-2xl px-4 py-3 ${status.tone === "good" ? "bg-good-bg text-good-ink" : "bg-danger-bg text-danger-ink"}`
            : "sr-only"
        }
      >
        {status?.message ?? ""}
      </p>
      {cats.data && peopleQ.data && (
        <>
          <NoteForm groups={cats.data} people={peopleQ.data} notify={notify} />
          <Notes notify={notify} />
          <People groups={cats.data} people={peopleQ.data} notify={notify} />
        </>
      )}
      {(cats.error || peopleQ.error) && (
        <p className="mt-6 rounded-2xl bg-danger-bg px-4 py-3 text-danger-ink">
          Could not load: {((cats.error ?? peopleQ.error) as Error).message}
        </p>
      )}
    </section>
  );
}
