import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default withSentryConfig(nextConfig, {
  silent: !process.env.CI,
  telemetry: false,
  sourcemaps: {
    disable: !process.env.SENTRY_AUTH_TOKEN,
  },
});
