import pluginQuery from "@tanstack/eslint-plugin-query";
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";
import jsxA11y from "eslint-plugin-jsx-a11y";

export default defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  ...pluginQuery.configs["flat/recommended"],
  {
    // eslint-config-next registers the jsx-a11y plugin but enables only a handful of its
    // rules as warnings; the shop has to be accessible, so the full recommended set applies.
    name: "modellbahn/accessibility",
    files: ["**/*.tsx"],
    rules: {
      ...jsxA11y.flatConfigs.recommended.rules,
      // Our form controls render a native <input>, <select> or <textarea> inside.
      "jsx-a11y/label-has-associated-control": [
        "error",
        { controlComponents: ["Input", "Select", "Textarea", "PasswordInput"], depth: 3 },
      ],
    },
  },
  {
    name: "modellbahn/rules",
    rules: {
      "@typescript-eslint/consistent-type-imports": ["error", { fixStyle: "inline-type-imports" }],
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", ignoreRestSiblings: true },
      ],
      "@typescript-eslint/no-unused-expressions": "error",
      eqeqeq: ["error", "always"],
      "no-console": ["error", { allow: ["warn", "error"] }],
      "import/no-duplicates": "error",
      "react/jsx-no-useless-fragment": "error",
      "react/self-closing-comp": "error",
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "coverage/**",
    "next-env.d.ts",
    // Generated from openapi.json by Orval (`npm run client`); never edited by hand.
    "src/lib/api/generated/**",
  ]),
]);
