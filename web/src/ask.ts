// A way for any page to open Ask Claude with a question written in (ADR-101): the "Explain"
// buttons use it. The question is only written in; the person sends it, because it costs.

const EVENT = "ask-claude";

export function askAbout(question: string) {
  window.dispatchEvent(new CustomEvent<string>(EVENT, { detail: question }));
}

/** Call `open` with the question whenever a page asks; returns how to stop listening. */
export function onAsk(open: (question: string) => void): () => void {
  const heard = (e: Event) => open((e as CustomEvent<string>).detail);
  window.addEventListener(EVENT, heard);
  return () => window.removeEventListener(EVENT, heard);
}
