import {
    fireEvent,
    render,
    RenderResult,
    waitFor,
} from "@testing-library/react";
import React from "react";
import { describe, expect, test, vi } from "vitest";
import type {
    GeneratedRegionalCloudCatalog,
    RegionalCloudInstance,
    RegionalCloudProvider,
} from "@/data/regionalClouds";
import { useSelected } from "@/state";
import RegionalCloudIndex from "./RegionalCloudIndex";

const navigation = vi.hoisted(() => ({ pathname: "/regional-cloud-test" }));

vi.mock("next/navigation", () => ({
    usePathname: () => navigation.pathname,
}));

vi.mock("@/utils/abGroup", () => ({
    abGroup: false,
    browserBlockingLocalStorage: true,
}));

vi.mock("@/utils/instancesKvClient", () => ({
    get: vi.fn().mockRejectedValue(new Error("No saved test state")),
    write: vi.fn().mockResolvedValue("test-state"),
}));

vi.mock("@/components/InstanceTable", async () => {
    const React = await import("react");
    const { useCompareOn, useSearchTerm, useSelected } = await import(
        "@/state"
    );
    const { usePathname } = await import("next/navigation");

    return {
        default: function MockInstanceTable({
            instances,
            instanceCount,
            columnAtomKey,
        }: {
            instances: Array<{ instance_type: string }>;
            instanceCount: number;
            columnAtomKey: string;
        }) {
            const pathname = usePathname();
            const [compareOn] = useCompareOn(pathname);
            const [selected] = useSelected(pathname);
            const [searchTerm] = useSearchTerm(pathname);
            const normalizedSearch = searchTerm.toLowerCase();
            const displayedInstances = instances.filter((instance) => {
                if (compareOn && !selected.includes(instance.instance_type)) {
                    return false;
                }
                return (
                    !normalizedSearch ||
                    JSON.stringify(instance)
                        .toLowerCase()
                        .includes(normalizedSearch)
                );
            });

            return React.createElement(
                "section",
                {
                    "data-testid": "instance-table",
                    "data-column-key": columnAtomKey,
                    "data-instance-count": String(instanceCount),
                    "data-rendered-count": String(displayedInstances.length),
                    "data-search-term": searchTerm,
                    "data-compare-on": String(compareOn),
                },
                displayedInstances.map((instance) =>
                    React.createElement(
                        "span",
                        { key: instance.instance_type },
                        instance.instance_type,
                    ),
                ),
            );
        },
    };
});

function instance(
    instanceType: string,
    regions: string[],
): RegionalCloudInstance {
    return {
        instanceType,
        family: "g8i",
        familyName: "General-purpose g8i",
        category: "General purpose",
        vCPU: 2,
        memoryGiB: 8,
        architecture: "x86_64",
        processor: "Intel Xeon",
        networkPerformance: "Up to 15 Gbps",
        localStorage: "Cloud disks",
        sourceUrl:
            "https://www.alibabacloud.com/help/en/ecs/user-guide/instance-families",
        regions,
        zones: regions.map((region) => `${region}-a`),
    };
}

const initialProvider: RegionalCloudProvider = {
    slug: "alibaba",
    name: "Alibaba Cloud",
    nativeName: "阿里云",
    productName: "Elastic Compute Service (ECS)",
    catalogName: "Alibaba Cloud ECS",
    description: "Test catalog",
    documentationUrl:
        "https://www.alibabacloud.com/help/en/ecs/user-guide/instance-families",
    pricingUrl: "https://www.alibabacloud.com/pricing-calculator",
    lastReviewed: "2026-07-10",
    coverageNote: "Stable component test fixture.",
    dataSource: "curated",
    instances: [
        instance("ecs.beijing.large", ["cn-beijing"]),
        instance("ecs.shanghai.large", ["cn-shanghai"]),
        instance("ecs.shared.large", ["cn-beijing", "cn-shanghai"]),
    ],
};

const originalResizeObserver = window.ResizeObserver;
const originalScrollIntoView = Element.prototype.scrollIntoView;

function patchPopoverBrowserApis() {
    window.ResizeObserver = class {
        observe() {}
        disconnect() {}
        unobserve() {}
    };
    Element.prototype.scrollIntoView = function () {};
}

function restoreBrowserApis() {
    window.ResizeObserver = originalResizeObserver;
    Element.prototype.scrollIntoView = originalScrollIntoView;
    vi.unstubAllGlobals();
}

function setPathname(pathname: string) {
    navigation.pathname = pathname;
    window.history.replaceState({}, "", pathname);
}

function IndexWithSelectionControl({
    provider,
}: {
    provider: RegionalCloudProvider;
}) {
    const [, setSelected] = useSelected(navigation.pathname);

    return React.createElement(
        React.Fragment,
        null,
        React.createElement(
            "button",
            {
                type: "button",
                onClick: () => setSelected(["ecs.beijing.large"]),
            },
            "Select Beijing fixture",
        ),
        React.createElement(RegionalCloudIndex, { provider }),
    );
}

function table(component: RenderResult) {
    return component.getByTestId("instance-table");
}

describe("regional cloud index", () => {
    test("refreshes from the runtime snapshot using the deployment base path", async () => {
        setPathname("/regional-runtime-test");
        patchPopoverBrowserApis();

        const originalBasePath = process.env.NEXT_PUBLIC_BASE_PATH;
        process.env.NEXT_PUBLIC_BASE_PATH = "/ec2instances.info";
        const refreshedInstances = [
            instance("ecs.runtime.large", ["cn-runtime-1"]),
            instance("ecs.runtime.xlarge", ["cn-runtime-2"]),
        ];
        const snapshot: GeneratedRegionalCloudCatalog = {
            schemaVersion: 3,
            generatedAt: "2026-07-17T10:00:00Z",
            providers: {
                alibaba: {
                    slug: "alibaba",
                    regionCount: 2,
                    zoneCount: 2,
                    instances: refreshedInstances,
                },
            },
        };
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            json: vi.fn().mockResolvedValue(snapshot),
        });
        vi.stubGlobal("fetch", fetchMock);

        const component = render(
            React.createElement(RegionalCloudIndex, {
                provider: initialProvider,
            }),
        );

        try {
            expect(table(component).dataset.instanceCount).toBe("3");

            await waitFor(() => {
                expect(table(component).dataset.instanceCount).toBe("2");
            });

            expect(fetchMock).toHaveBeenCalledTimes(1);
            expect(fetchMock).toHaveBeenCalledWith(
                "/ec2instances.info/data/china-clouds.json",
                expect.objectContaining({
                    cache: "no-store",
                    signal: expect.any(AbortSignal),
                }),
            );
            expect(table(component).textContent).toContain("ecs.runtime.large");
            expect(table(component).textContent).not.toContain(
                "ecs.beijing.large",
            );
            expect(table(component).dataset.columnKey).toBe("regionalCloud");
        } finally {
            component.unmount();
            restoreBrowserApis();
            if (originalBasePath === undefined) {
                delete process.env.NEXT_PUBLIC_BASE_PATH;
            } else {
                process.env.NEXT_PUBLIC_BASE_PATH = originalBasePath;
            }
        }
    });

    test("wires region, compare, and search controls into table state", async () => {
        setPathname("/regional-filter-test");
        patchPopoverBrowserApis();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockRejectedValue(new TypeError("Snapshot unavailable")),
        );

        const component = render(
            React.createElement(IndexWithSelectionControl, {
                provider: initialProvider,
            }),
        );

        try {
            expect(table(component).dataset.instanceCount).toBe("3");

            fireEvent.click(component.getByLabelText("Region"));
            const shanghaiOption = component.baseElement.querySelector(
                "div[data-value='cn-shanghai']",
            );
            expect(shanghaiOption).toBeTruthy();
            fireEvent.click(shanghaiOption as Element);

            await waitFor(() => {
                expect(table(component).dataset.instanceCount).toBe("2");
            });
            expect(table(component).textContent).toContain(
                "ecs.shanghai.large",
            );
            expect(table(component).textContent).toContain("ecs.shared.large");
            expect(table(component).textContent).not.toContain(
                "ecs.beijing.large",
            );

            fireEvent.click(
                component.getByRole("button", {
                    name: "Select Beijing fixture",
                }),
            );
            const compare = component.getByRole("button", { name: "Compare" });
            expect((compare as HTMLButtonElement).disabled).toBe(false);
            fireEvent.click(compare);

            await waitFor(() => {
                expect(table(component).dataset.compareOn).toBe("true");
            });
            expect(table(component).dataset.instanceCount).toBe("3");
            expect(table(component).dataset.renderedCount).toBe("1");
            expect(table(component).textContent).toContain("ecs.beijing.large");
            expect(
                component.getByRole("button", { name: "End Compare" }),
            ).toBeTruthy();

            fireEvent.click(
                component.getByRole("button", { name: "End Compare" }),
            );
            const search = component.getByPlaceholderText("Search...");
            fireEvent.change(search, { target: { value: "shared" } });

            await waitFor(() => {
                expect(table(component).dataset.searchTerm).toBe("shared");
            });
            expect(table(component).dataset.renderedCount).toBe("1");
            expect(table(component).textContent).toBe("ecs.shared.large");
        } finally {
            component.unmount();
            restoreBrowserApis();
        }
    });
});
