// Category colors from the Mercado design system (docs/design-system.md).
// Charts and category chips read these CSS variables so dark mode follows automatically.
export const CATEGORY_COLORS: Record<string, string> = {
  "Fixed bills": "var(--color-cat-fixed)",
  Groceries: "var(--color-cat-groceries)",
  Health: "var(--color-cat-health)",
  Services: "var(--color-cat-services)",
  "Dining out": "var(--color-cat-dining)",
  Shopping: "var(--color-cat-shopping)",
  Subscriptions: "var(--color-cat-subscriptions)",
  "Food delivery": "var(--color-cat-delivery)",
  Kids: "var(--color-cat-kids)",
  Transport: "var(--color-cat-transport)",
};

export const FALLBACK_CATEGORY_COLOR = "var(--color-muted)";

export function categoryColor(name: string): string {
  return CATEGORY_COLORS[name] ?? FALLBACK_CATEGORY_COLOR;
}
