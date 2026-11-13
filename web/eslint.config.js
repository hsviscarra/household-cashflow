import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

const MAX_LINES = 400;
// Files that were over the limit when it was set (0.111.0). Nothing new is added to this list:
// a file leaves it when it is split (docs/refactors.md #4 and #13).
const BASELINE = [
  "src/App.tsx",
  "src/api.ts",
  "src/components/CategoryPicker.tsx",
  "src/components/DataTable.tsx",
  "src/components/MerchantReview.tsx",
  "src/components/charts.tsx",
  "src/pages/Bills.tsx",
  "src/pages/CashFlow.tsx",
  "src/pages/GroceryTrends.tsx",
  "src/pages/Home.tsx",
  "src/pages/ImportStatements.tsx",
  "src/pages/NetWorth.tsx",
  "src/pages/Overview.tsx",
  "src/pages/People.tsx",
  "src/pages/Projections.tsx",
  "src/pages/Purchases.tsx",
  "src/pages/Recurring.tsx",
  "src/pages/Settings.tsx",
  "src/pages/Spending.tsx",
  "src/pages/Status.tsx",
  "src/pages/Taxes.tsx",
  "src/pages/Todo.tsx",
  "src/pages/Transactions.tsx",
];

export default tseslint.config(
  { ignores: ["dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Code standard (ADR-102): one file, one reason to change.
      "max-lines": ["error", { max: MAX_LINES, skipBlankLines: true, skipComments: true }],
    },
  },
  { files: ["**/*.test.{ts,tsx}", "e2e/**"], rules: { "max-lines": "off" } },
  { files: BASELINE, rules: { "max-lines": "off" } },
);
