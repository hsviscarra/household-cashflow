import { useId, useState } from "react";

import { EXPLAIN, type ExplainKey, type Explanation } from "../explain";

/** An ⓘ next to a number or a title (ADR-073): what it means, how it is calculated and what it
 * leaves out, from one place (explain.ts) so the same number always says the same thing. Opens on
 * hover, focus or tap. */
export default function Info({ k, className = "" }: { k: ExplainKey; className?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const e: Explanation = EXPLAIN[k];
  return (
    <span className={`relative inline-block align-middle ${className}`}>
      <button
        type="button"
        aria-label={`What is ${e.title}?`}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onBlur={() => setOpen(false)}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-line text-[10px] font-bold leading-none text-muted hover:text-ink"
      >
        i
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute left-1/2 top-6 z-30 block w-72 -translate-x-1/2 rounded-xl border border-line bg-ground p-3 text-left text-sm font-normal normal-case tracking-normal text-ink shadow-lg"
        >
          <span className="block font-semibold">{e.title}</span>
          <span className="mt-1 block">{e.what}</span>
          {e.how && (
            <span className="mt-2 block text-muted">
              <span className="font-semibold">How it’s calculated: </span>
              {e.how}
            </span>
          )}
          {e.excludes && (
            <span className="mt-1 block text-muted">
              <span className="font-semibold">Doesn’t include: </span>
              {e.excludes}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
