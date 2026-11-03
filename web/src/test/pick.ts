import { fireEvent, within } from "@testing-library/react";

/** Choose a category in a CategoryPicker: type `search` in its box, then click the option. */
export function pickCategory(box: HTMLElement, search: string, option: string | RegExp = search): void {
  fireEvent.focus(box);
  fireEvent.change(box, { target: { value: search } });
  const list = document.getElementById(box.getAttribute("aria-controls") ?? "");
  if (!list) throw new Error("The category list did not open.");
  fireEvent.click(
    within(list).getByRole("option", { name: new RegExp(option instanceof RegExp ? option.source : option) }),
  );
}
