"use client";

import type {
    RegionalCloudInstance,
    RegionalCloudProvider,
} from "@/data/regionalClouds";
import { ArrowDown, ArrowUp, ExternalLink, Search } from "lucide-react";
import { useMemo, useState } from "react";

type SortKey = "instanceType" | "family" | "vCPU" | "memoryGiB";
type SortDirection = "ascending" | "descending";

function compareInstances(
    left: RegionalCloudInstance,
    right: RegionalCloudInstance,
    sortKey: SortKey,
) {
    if (sortKey === "vCPU" || sortKey === "memoryGiB") {
        return left[sortKey] - right[sortKey];
    }
    return left[sortKey].localeCompare(right[sortKey], undefined, {
        numeric: true,
    });
}

function SortButton({
    active,
    direction,
    label,
    onClick,
}: {
    active: boolean;
    direction: SortDirection;
    label: string;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            className="flex w-full items-center gap-1 text-left font-semibold"
            onClick={onClick}
        >
            {label}
            {active &&
                (direction === "ascending" ? (
                    <ArrowUp aria-hidden="true" className="h-3.5 w-3.5" />
                ) : (
                    <ArrowDown aria-hidden="true" className="h-3.5 w-3.5" />
                ))}
        </button>
    );
}

function memoryPerVcpu(instance: RegionalCloudInstance) {
    return Math.round((instance.memoryGiB / instance.vCPU) * 100) / 100;
}

export default function RegionalCloudCatalog({
    provider,
}: {
    provider: RegionalCloudProvider;
}) {
    const [search, setSearch] = useState("");
    const [category, setCategory] = useState("all");
    const [architecture, setArchitecture] = useState("all");
    const [sortKey, setSortKey] = useState<SortKey>("instanceType");
    const [sortDirection, setSortDirection] =
        useState<SortDirection>("ascending");
    const [selected, setSelected] = useState<string[]>([]);
    const [compareOnly, setCompareOnly] = useState(false);

    const categories = useMemo(
        () => [...new Set(provider.instances.map((item) => item.category))],
        [provider.instances],
    );
    const architectures = useMemo(
        () => [...new Set(provider.instances.map((item) => item.architecture))],
        [provider.instances],
    );

    const visibleInstances = useMemo(() => {
        const normalizedSearch = search.trim().toLowerCase();
        return provider.instances
            .filter((instance) => {
                if (compareOnly && !selected.includes(instance.instanceType)) {
                    return false;
                }
                if (category !== "all" && instance.category !== category) {
                    return false;
                }
                if (
                    architecture !== "all" &&
                    instance.architecture !== architecture
                ) {
                    return false;
                }
                if (!normalizedSearch) return true;
                return [
                    instance.instanceType,
                    instance.family,
                    instance.familyName,
                    instance.category,
                    instance.processor,
                    ...(instance.regions ?? []),
                    ...(instance.zones ?? []),
                ].some((value) =>
                    value.toLowerCase().includes(normalizedSearch),
                );
            })
            .sort((left, right) => {
                const result = compareInstances(left, right, sortKey);
                return sortDirection === "ascending" ? result : -result;
            });
    }, [
        architecture,
        category,
        compareOnly,
        provider.instances,
        search,
        selected,
        sortDirection,
        sortKey,
    ]);

    function changeSort(nextSortKey: SortKey) {
        if (nextSortKey === sortKey) {
            setSortDirection((current) =>
                current === "ascending" ? "descending" : "ascending",
            );
            return;
        }
        setSortKey(nextSortKey);
        setSortDirection("ascending");
    }

    function toggleSelected(instanceType: string) {
        setSelected((current) =>
            current.includes(instanceType)
                ? current.filter((value) => value !== instanceType)
                : [...current, instanceType],
        );
    }

    function clearSelection() {
        setSelected([]);
        setCompareOnly(false);
    }

    return (
        <main className="flex min-h-[calc(100vh-6rem)] flex-col">
            <section className="border-b border-gray-3 bg-gray-4 px-4 py-5">
                <div className="mx-auto flex max-w-screen-2xl flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div className="max-w-3xl">
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                            <h1 className="text-2xl font-bold">
                                {provider.catalogName} Instance Comparison
                            </h1>
                            <span className="rounded-full border border-gray-3 bg-background px-2 py-0.5 text-xs">
                                {provider.nativeName}
                            </span>
                            <span className="rounded-full border border-gray-3 bg-background px-2 py-0.5 text-xs">
                                {provider.dataSource === "api"
                                    ? "Live API data"
                                    : "Curated fallback"}
                            </span>
                        </div>
                        <p className="text-sm text-gray-2">
                            {provider.description}
                        </p>
                        <p className="mt-2 text-xs text-gray-2">
                            {provider.coverageNote}{" "}
                            {provider.dataSource === "api"
                                ? "Snapshot generated on "
                                : "Specifications reviewed on "}
                            <time dateTime={provider.lastReviewed}>
                                {provider.lastReviewed}
                            </time>
                            . Prices are not copied into this catalog because
                            they depend on region, billing term, image, and
                            account discounts.
                        </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                        <a
                            className="btn btn-outline-secondary inline-flex items-center gap-1.5"
                            href={provider.documentationUrl}
                            target="_blank"
                            rel="noreferrer"
                        >
                            Official specifications
                            <ExternalLink
                                aria-hidden="true"
                                className="h-3.5 w-3.5"
                            />
                        </a>
                        <a
                            className="btn btn-purple inline-flex items-center gap-1.5"
                            href={provider.pricingUrl}
                            target="_blank"
                            rel="noreferrer"
                        >
                            Price calculator
                            <ExternalLink
                                aria-hidden="true"
                                className="h-3.5 w-3.5"
                            />
                        </a>
                    </div>
                </div>
            </section>

            <section
                aria-label="Catalog controls"
                className="border-b border-gray-3 px-4 py-3"
            >
                <div className="mx-auto flex max-w-screen-2xl flex-wrap items-end gap-3">
                    <label className="flex min-w-64 flex-1 flex-col gap-1 text-xs font-medium">
                        Search
                        <span className="relative">
                            <Search
                                aria-hidden="true"
                                className="absolute left-2 top-2 h-4 w-4 text-gray-2"
                            />
                            <input
                                className="form-control w-full rounded-md border border-gray-3 bg-background py-1.5 pl-8 pr-2 text-sm text-foreground"
                                type="search"
                                value={search}
                                onChange={(event) =>
                                    setSearch(event.target.value)
                                }
                                placeholder="Instance type, family, or processor"
                            />
                        </span>
                    </label>
                    <label className="flex flex-col gap-1 text-xs font-medium">
                        Category
                        <select
                            className="form-select py-1.5"
                            value={category}
                            onChange={(event) =>
                                setCategory(event.target.value)
                            }
                        >
                            <option value="all">All categories</option>
                            {categories.map((value) => (
                                <option key={value} value={value}>
                                    {value}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className="flex flex-col gap-1 text-xs font-medium">
                        Architecture
                        <select
                            className="form-select py-1.5"
                            value={architecture}
                            onChange={(event) =>
                                setArchitecture(event.target.value)
                            }
                        >
                            <option value="all">All architectures</option>
                            {architectures.map((value) => (
                                <option key={value} value={value}>
                                    {value}
                                </option>
                            ))}
                        </select>
                    </label>
                    <button
                        type="button"
                        className="btn btn-purple disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={selected.length < 2}
                        onClick={() => setCompareOnly((current) => !current)}
                    >
                        {compareOnly
                            ? "Show all matching"
                            : `Compare selected (${selected.length})`}
                    </button>
                    <button
                        type="button"
                        className="btn btn-outline-secondary disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={selected.length === 0}
                        onClick={clearSelection}
                    >
                        Clear selection
                    </button>
                    <p
                        aria-live="polite"
                        className="ml-auto text-sm text-gray-2"
                    >
                        {visibleInstances.length} of {provider.instances.length}{" "}
                        unique instance types
                    </p>
                </div>
            </section>

            <div className="mx-auto w-full max-w-screen-2xl flex-1 overflow-auto">
                <table className="index-table min-w-[1320px]">
                    <caption className="sr-only">
                        {provider.catalogName} instance catalog
                    </caption>
                    <thead>
                        <tr>
                            <th className="w-12 px-2 py-3">
                                <span className="sr-only">Select</span>
                            </th>
                            <th className="w-52 px-2 py-3">
                                <SortButton
                                    label="Instance type"
                                    active={sortKey === "instanceType"}
                                    direction={sortDirection}
                                    onClick={() => changeSort("instanceType")}
                                />
                            </th>
                            <th className="w-52 px-2 py-3">
                                <SortButton
                                    label="Family"
                                    active={sortKey === "family"}
                                    direction={sortDirection}
                                    onClick={() => changeSort("family")}
                                />
                            </th>
                            <th className="w-40 px-2 py-3">Category</th>
                            <th className="w-20 px-2 py-3">
                                <SortButton
                                    label="vCPUs"
                                    active={sortKey === "vCPU"}
                                    direction={sortDirection}
                                    onClick={() => changeSort("vCPU")}
                                />
                            </th>
                            <th className="w-28 px-2 py-3">
                                <SortButton
                                    label="Memory"
                                    active={sortKey === "memoryGiB"}
                                    direction={sortDirection}
                                    onClick={() => changeSort("memoryGiB")}
                                />
                            </th>
                            <th className="w-28 px-2 py-3">Memory/vCPU</th>
                            <th className="w-28 px-2 py-3">Architecture</th>
                            <th className="w-20 px-2 py-3">Regions</th>
                            <th className="w-20 px-2 py-3">Zones</th>
                            <th className="w-64 px-2 py-3">Processor</th>
                            <th className="w-64 px-2 py-3">
                                Network performance
                            </th>
                            <th className="w-36 px-2 py-3">Storage</th>
                            <th className="w-20 px-2 py-3">Source</th>
                        </tr>
                    </thead>
                    <tbody>
                        {visibleInstances.map((instance) => (
                            <tr
                                key={instance.instanceType}
                                className={
                                    selected.includes(instance.instanceType)
                                        ? "row-selected"
                                        : undefined
                                }
                            >
                                <td>
                                    <input
                                        type="checkbox"
                                        aria-label={`Select ${instance.instanceType} for comparison`}
                                        checked={selected.includes(
                                            instance.instanceType,
                                        )}
                                        onChange={() =>
                                            toggleSelected(
                                                instance.instanceType,
                                            )
                                        }
                                    />
                                </td>
                                <td className="font-mono font-medium">
                                    {instance.instanceType}
                                </td>
                                <td>{instance.familyName}</td>
                                <td>{instance.category}</td>
                                <td>{instance.vCPU}</td>
                                <td>{instance.memoryGiB} GiB</td>
                                <td>{memoryPerVcpu(instance)} GiB</td>
                                <td>{instance.architecture}</td>
                                <td title={(instance.regions ?? []).join(", ")}>
                                    {instance.availableRegionCount ??
                                        instance.regions?.length ??
                                        "—"}
                                </td>
                                <td title={(instance.zones ?? []).join(", ")}>
                                    {instance.availableZoneCount ??
                                        instance.zones?.length ??
                                        "—"}
                                </td>
                                <td>{instance.processor}</td>
                                <td>{instance.networkPerformance}</td>
                                <td>{instance.localStorage}</td>
                                <td>
                                    <a
                                        href={instance.sourceUrl}
                                        target="_blank"
                                        rel="noreferrer"
                                        aria-label={`Open the official specification for ${instance.instanceType}`}
                                    >
                                        Official
                                    </a>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                {visibleInstances.length === 0 && (
                    <p className="p-8 text-center text-sm text-gray-2">
                        No instances match the current filters.
                    </p>
                )}
            </div>
        </main>
    );
}
