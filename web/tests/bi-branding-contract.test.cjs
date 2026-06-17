const assert = require("assert");
const fs = require("fs");
const path = require("path");

function read(relPath) {
  return fs.readFileSync(path.join(__dirname, "..", relPath), "utf8");
}

const brandSource = read("lib/brand.ts");
const biApiSource = read("lib/bi-api.ts");
const biHeaderSource = read("app/(workspace)/bi/_components/BiBossHeader.tsx");

assert(
  brandSource.includes('export const BI_WORKBENCH_TITLE = `${APP_BRAND_NAME} BI 工作台`'),
  "brand authority should define the canonical BI workbench title once",
);
assert(
  biApiSource.includes("BI_WORKBENCH_TITLE"),
  "bi api fallback title should read from the shared BI workbench title authority",
);
assert(
  biHeaderSource.includes("BI_WORKBENCH_TITLE"),
  "bi header visible title should read from the shared BI workbench title authority",
);
assert(
  !brandSource.includes("DeepTutor BI 工作台") &&
    !biApiSource.includes("DeepTutor BI 工作台") &&
    !biHeaderSource.includes("DeepTutor BI 工作台"),
  "bi title authority should not keep the old DeepTutor BI literal",
);

console.log("PASS bi-branding-contract.test.cjs");
