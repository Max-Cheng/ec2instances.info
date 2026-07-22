import { describe, expect, test } from "vitest";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
    columnsGen,
    initialColumnsValue,
    makePrettyNames,
    resolveRegionalCloudPrice,
    resolveRegionalCloudSpotPrice,
    resolveRegionalCloudSubscriptionPrice,
} from "./regionalCloud";

const tableInstance = {
    instanceType: "ecs.g8i.large",
    instance_type: "ecs.g8i.large",
    family: "g8i",
    familyName: "General-purpose g8i",
    category: "General purpose" as const,
    vCPU: 2,
    memoryGiB: 8,
    memoryPerVcpu: 4,
    architecture: "x86_64" as const,
    processor: "Intel Xeon",
    networkPerformance: "Up to 15 Gbps",
    localStorage: "Cloud disks",
    sourceUrl: "https://example.com/specs",
    pricingUrl: "https://www.alibabacloud.com/pricing-calculator",
    regions: ["cn-beijing", "cn-shanghai"],
    zones: ["cn-beijing-a", "cn-shanghai-a"],
    availableRegionCount: 2,
    availableZoneCount: 2,
    onDemandPrices: {
        "cn-beijing": {
            amount: "0.5",
            currency: "CNY" as const,
            unit: "hour" as const,
        },
        "cn-shanghai": {
            amount: "0.8",
            currency: "CNY" as const,
            unit: "hour" as const,
        },
    },
    subscriptionPrices: {
        "cn-beijing": {
            amount: "0.3",
            totalAmount: "2628",
            currency: "CNY" as const,
            unit: "hour" as const,
            term: "1-year" as const,
            payment: "all-upfront" as const,
        },
        "cn-shanghai": {
            amount: "0.4",
            totalAmount: "3504",
            currency: "CNY" as const,
            unit: "hour" as const,
            term: "1-year" as const,
            payment: "all-upfront" as const,
        },
    },
    spotPrices: {
        "cn-beijing": {
            amount: "0.12",
            currency: "CNY" as const,
            unit: "hour" as const,
            zone: "cn-beijing-a",
            observedAt: "2026-07-22T00:00:00Z",
        },
        "cn-shanghai": {
            amount: "0.18",
            currency: "CNY" as const,
            unit: "hour" as const,
        },
    },
};

describe("regional cloud columns", () => {
    test("does not expose availability counts or source links as columns", () => {
        const optionKeys = makePrettyNames((key) => key);
        const columnIds = columnsGen("all", "instance", "hourly", "", {
            code: "USD",
            usdRate: 1,
            cnyRate: 1,
        }).map((column) => column.id);

        expect(initialColumnsValue).not.toHaveProperty("availableRegionCount");
        expect(initialColumnsValue).not.toHaveProperty("sourceUrl");
        expect(initialColumnsValue.pricingUrl).toBe(true);
        expect(initialColumnsValue.subscriptionPricingUrl).toBe(true);
        expect(initialColumnsValue.spotPricingUrl).toBe(true);
        expect(optionKeys).not.toContain("availableRegionCount");
        expect(optionKeys).not.toContain("sourceUrl");
        expect(columnIds).not.toContain("availableRegionCount");
        expect(columnIds).not.toContain("sourceUrl");
        expect(optionKeys).toContain("pricingUrl");
        expect(columnIds).toContain("pricingUrl");
        expect(optionKeys).toContain("subscriptionPricingUrl");
        expect(optionKeys).toContain("spotPricingUrl");
        expect(columnIds).toContain("subscriptionPricingUrl");
        expect(columnIds).toContain("spotPricingUrl");
    });

    test("renders the provider calculator when the selected region has no numeric price", () => {
        const pricingColumn = columnsGen("all", "instance", "hourly", "", {
            code: "USD",
            usdRate: 1,
            cnyRate: 1,
        }).find((column) => column.id === "pricingUrl");
        const cell = pricingColumn?.cell;

        expect(typeof cell).toBe("function");
        const markup = renderToStaticMarkup(
            (cell as (info: unknown) => ReactNode)({
                row: {
                    original: {
                        ...tableInstance,
                        onDemandPrices: undefined,
                    },
                },
            }),
        );

        expect(markup).toContain(
            'href="https://www.alibabacloud.com/pricing-calculator"',
        );
        expect(markup).toContain('aria-label="View pricing for ecs.g8i.large"');
        expect(markup).toContain("View pricing");
    });

    test("uses the selected region price and the explicit source currency", () => {
        const price = resolveRegionalCloudPrice(
            tableInstance,
            "cn-shanghai",
            "instance",
            "hourly",
        );
        expect(price).toMatchObject({
            region: "cn-shanghai",
            fromMultipleRegions: false,
        });
        expect(price?.value).toBe(0.8);
    });

    test("resolves one-year subscription and spot prices independently", () => {
        expect(
            resolveRegionalCloudSubscriptionPrice(
                tableInstance,
                "cn-shanghai",
                "instance",
                "hourly",
            )?.value,
        ).toBe(0.4);
        expect(
            resolveRegionalCloudSpotPrice(
                tableInstance,
                "cn-shanghai",
                "instance",
                "hourly",
            )?.value,
        ).toBe(0.18);
    });

    test("renders the lowest collected regional price in the all-regions view", () => {
        const pricingColumn = columnsGen("all", "instance", "hourly", "", {
            code: "USD",
            usdRate: 1,
            cnyRate: 0.14,
        }).find((column) => column.id === "pricingUrl");
        const cell = pricingColumn?.cell;
        const markup = renderToStaticMarkup(
            (cell as (info: unknown) => ReactNode)({
                row: { original: tableInstance },
            }),
        );

        expect(markup).toContain("From ¥0.50 / hr");
        expect(markup).toContain("cn-beijing");
    });

    test("renders truthful subscription total and spot quote metadata", () => {
        const columns = columnsGen("cn-beijing", "instance", "hourly", "", {
            code: "USD",
            usdRate: 1,
            cnyRate: 0.14,
        });
        const renderCell = (columnId: string) => {
            const cell = columns.find((column) => column.id === columnId)?.cell;
            return renderToStaticMarkup(
                (cell as (info: unknown) => ReactNode)({
                    row: { original: tableInstance },
                }),
            );
        };

        const subscriptionMarkup = renderCell("subscriptionPricingUrl");
        expect(subscriptionMarkup).toContain("¥0.30 / hr");
        expect(subscriptionMarkup).toContain("¥2,628.00 total");
        expect(subscriptionMarkup).toContain("all-upfront subscription");

        const spotMarkup = renderCell("spotPricingUrl");
        expect(spotMarkup).toContain("¥0.12 / hr");
        expect(spotMarkup).toContain("cn-beijing-a");
        expect(spotMarkup).toContain("2026-07-22T00:00:00Z");
    });
});
