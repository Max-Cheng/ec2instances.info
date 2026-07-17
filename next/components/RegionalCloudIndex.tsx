"use client";

import InstanceTable from "@/components/InstanceTable";
import RegionalCloudFilters from "@/components/RegionalCloudFilters";
import type {
    GeneratedRegionalCloudCatalog,
    RegionalCloudProvider,
} from "@/data/regionalClouds";
import { resolveRegionalCloudProvider } from "@/data/regionalClouds";
import { useCompareOn } from "@/state";
import { withBasePath } from "@/utils/deploymentPaths";
import {
    adaptRegionalCloudInstance,
    regionalCloudRegionIds,
} from "@/utils/regionalCloudTableAdapter";
import { useGlobalStateValue } from "@/utils/useGlobalStateValue";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

export default function RegionalCloudIndex({
    provider: initialProvider,
}: {
    provider: RegionalCloudProvider;
}) {
    const pathname = usePathname();
    const [provider, setProvider] = useState(initialProvider);
    const [selectedRegion] = useGlobalStateValue("region", pathname, "all");
    const [compareOn] = useCompareOn(pathname);

    useEffect(() => {
        const controller = new AbortController();
        let active = true;
        setProvider(initialProvider);

        async function refreshProvider() {
            const response = await fetch(
                withBasePath("/data/china-clouds.json"),
                {
                    cache: "no-store",
                    signal: controller.signal,
                },
            );
            if (!response.ok) {
                throw new Error(
                    `China cloud catalog returned HTTP ${response.status}`,
                );
            }

            const catalog =
                (await response.json()) as GeneratedRegionalCloudCatalog;
            if (catalog.schemaVersion !== 1) {
                throw new Error(
                    `Unsupported China cloud catalog schema ${catalog.schemaVersion}`,
                );
            }
            if (active) {
                setProvider(
                    resolveRegionalCloudProvider(initialProvider.slug, catalog),
                );
            }
        }

        void refreshProvider().catch((error: unknown) => {
            if (
                !(error instanceof DOMException) ||
                error.name !== "AbortError"
            ) {
                // Keep the build-time snapshot when the daily JSON is not
                // reachable. A later page load will try the refresh again.
            }
        });

        return () => {
            active = false;
            controller.abort();
        };
    }, [initialProvider]);

    const instances = useMemo(
        () => provider.instances.map(adaptRegionalCloudInstance),
        [provider.instances],
    );
    const regions = useMemo(
        () => regionalCloudRegionIds(instances),
        [instances],
    );
    const visibleInstances = useMemo(() => {
        if (compareOn || selectedRegion === "all") return instances;
        return instances.filter((instance) =>
            instance.regions.includes(selectedRegion),
        );
    }, [compareOn, instances, selectedRegion]);

    return (
        <main className="h-[calc(100vh-6em)] overflow-y-hidden flex flex-col">
            <RegionalCloudFilters regions={regions} />
            <div className="flex-1 min-h-0">
                <InstanceTable
                    instances={visibleInstances}
                    instanceCount={visibleInstances.length}
                    columnAtomKey="regionalCloud"
                />
            </div>
        </main>
    );
}
