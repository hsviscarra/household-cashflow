import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

const MAX_LINES = 400;
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
);
