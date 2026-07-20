import { describe, expect, test } from "vitest";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
    columnsGen,
    initialColumnsValue,
    makePrettyNames,
} from "./regionalCloud";

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
        expect(optionKeys).not.toContain("availableRegionCount");
        expect(optionKeys).not.toContain("sourceUrl");
        expect(columnIds).not.toContain("availableRegionCount");
        expect(columnIds).not.toContain("sourceUrl");
        expect(optionKeys).toContain("pricingUrl");
        expect(columnIds).toContain("pricingUrl");
    });

    test("renders the provider calculator as a pricing link", () => {
        const pricingColumn = columnsGen("all", "instance", "hourly", "", {
            code: "USD",
            usdRate: 1,
            cnyRate: 1,
        }).find((column) => column.id === "pricingUrl");
        const cell = pricingColumn?.cell;

        expect(typeof cell).toBe("function");
        const markup = renderToStaticMarkup(
            (cell as (info: unknown) => ReactNode)({
                getValue: () =>
                    "https://www.alibabacloud.com/pricing/calculator",
                row: {
                    original: { instance_type: "ecs.g8i.large" },
                },
            }),
        );

        expect(markup).toContain(
            'href="https://www.alibabacloud.com/pricing/calculator"',
        );
        expect(markup).toContain('aria-label="View ecs.g8i.large pricing"');
        expect(markup).toContain("View pricing");
    });
});
