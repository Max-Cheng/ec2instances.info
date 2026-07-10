import { afterEach, expect, test } from "vitest";
import {
    instanceDetailHref,
    rawAnchorHref,
    withBasePath,
} from "./deploymentPaths";

const originalBasePath = process.env.NEXT_PUBLIC_BASE_PATH;
const originalDetailOrigin = process.env.NEXT_PUBLIC_INSTANCE_DETAIL_ORIGIN;

afterEach(() => {
    process.env.NEXT_PUBLIC_BASE_PATH = originalBasePath;
    process.env.NEXT_PUBLIC_INSTANCE_DETAIL_ORIGIN = originalDetailOrigin;
});

test("prefixes root-relative assets with the deployment base path", () => {
    process.env.NEXT_PUBLIC_BASE_PATH = "/ec2instances.info";
    expect(withBasePath("/favicon.png")).toBe("/ec2instances.info/favicon.png");
});

test("keeps the normal root deployment unchanged", () => {
    delete process.env.NEXT_PUBLIC_BASE_PATH;
    expect(withBasePath("/favicon.png")).toBe("/favicon.png");
});

test("prefixes only internal raw anchors", () => {
    process.env.NEXT_PUBLIC_BASE_PATH = "/ec2instances.info";
    expect(rawAnchorHref("/alibaba")).toBe("/ec2instances.info/alibaba");
    expect(rawAnchorHref("https://example.com/path")).toBe(
        "https://example.com/path",
    );
});

test("can send omitted static detail pages to the canonical site", () => {
    process.env.NEXT_PUBLIC_INSTANCE_DETAIL_ORIGIN =
        "https://instances.vantage.sh/";
    expect(instanceDetailHref("/aws/ec2/m7i.large")).toBe(
        "https://instances.vantage.sh/aws/ec2/m7i.large",
    );
});
