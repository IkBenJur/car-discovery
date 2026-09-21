import type { Config } from "@react-router/dev/config";

export default {
  // This is an SPA paired with a separate Go API, so no server-side rendering.
  ssr: false,
} satisfies Config;
