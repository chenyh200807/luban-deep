import nextConfig from "eslint-config-next";
import i18nPlugin from "./eslint/i18n-plugin.mjs";

const config = [
  ...nextConfig,
  {
    files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}"],
    plugins: {
      i18n: i18nPlugin,
    },
    rules: {
      // During migration keep as warning; change to "error" once phase2/3 complete.
      "i18n/no-literal-ui-text": "warn",
    },
  },
  {
    // public/luban-preview = 编译生成的自包含教学卡 bundle(含 vendored 运行时 support.js),非应用源码
    ignores: ["node_modules/**", ".next/**", "out/**", "public/luban-preview/**"],
  },
];

export default config;
