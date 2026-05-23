import { readBiFlagsFromEnv } from "@/lib/bi-feature-flags";
import BiPageClient from "./BiPageClient";
import BiV2Surface from "./_v2/BiV2Surface";

export const dynamic = "force-dynamic";

export default function BiPage() {
  const flags = readBiFlagsFromEnv();
  if (flags.BI_BACKOFFICE_V2_SHELL_ENABLED) {
    return <BiV2Surface flags={flags} />;
  }
  return <BiPageClient />;
}
