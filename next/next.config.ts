import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";
if (basePath && (!basePath.startsWith("/") || basePath.endsWith("/"))) {
    throw new Error(
        "NEXT_PUBLIC_BASE_PATH must start with / and must not end with /",
    );
}

let nextConfig: NextConfig = {
    output: "export",
    basePath,
    trailingSlash: process.env.PAGES_LITE_BUILD === "1",
    typescript: {
        ignoreBuildErrors: true,
    },
    turbopack: {
        root: __dirname,
    },
    productionBrowserSourceMaps: process.env.PAGES_LITE_BUILD !== "1",
};

if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
    nextConfig = withSentryConfig(nextConfig, {
        org: process.env.SENTRY_ORG,
        project: process.env.SENTRY_PROJECT,
        disableLogger: true,
        authToken: process.env.SENTRY_AUTH_TOKEN,
        widenClientFileUpload: true,
        reactComponentAnnotation: {
            enabled: true,
        },
    });
}

export default nextConfig;
