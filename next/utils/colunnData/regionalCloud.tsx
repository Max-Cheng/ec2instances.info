import type { CostDuration, PricingUnit } from "@/types";
import type { RegionalCloudOnDemandPrice } from "@/data/regionalClouds";
import type { RegionalCloudTableInstance } from "@/utils/regionalCloudTableAdapter";
import type { ColumnDef } from "@tanstack/react-table";
import {
    expr,
    makeCellWithRegexSorter,
    regex,
    transformAllDataTables,
} from "./shared";

const HOUR_MULTIPLIERS: Record<CostDuration, number> = {
    secondly: 1 / 3600,
    minutely: 1 / 60,
    hourly: 1,
    daily: 24,
    weekly: 24 * 7,
    monthly: (24 * 365) / 12,
    annually: 24 * 365,
};

const DURATION_LABELS: Record<CostDuration, string> = {
    secondly: "sec",
    minutely: "min",
    hourly: "hr",
    daily: "day",
    weekly: "week",
    monthly: "mo",
    annually: "yr",
};

export type ResolvedRegionalCloudPrice = {
    value: number;
    region: string;
    source: RegionalCloudOnDemandPrice;
    fromMultipleRegions: boolean;
};

function pricingUnitDivisor(
    instance: RegionalCloudTableInstance,
    pricingUnit: PricingUnit,
): number | undefined {
    if (pricingUnit === "instance") return 1;
    if (pricingUnit === "vcpu") return instance.vCPU;
    if (pricingUnit === "memory") return instance.memoryGiB;
    return undefined;
}

export function resolveRegionalCloudPrice(
    instance: RegionalCloudTableInstance,
    selectedRegion: string,
    pricingUnit: PricingUnit,
    costDuration: CostDuration,
): ResolvedRegionalCloudPrice | undefined {
    const prices = instance.onDemandPrices ?? {};
    const candidates =
        selectedRegion === "all"
            ? Object.entries(prices)
            : prices[selectedRegion]
              ? ([[selectedRegion, prices[selectedRegion]]] as const)
              : [];
    const divisor = pricingUnitDivisor(instance, pricingUnit);
    if (!divisor || divisor <= 0) return undefined;

    let result: ResolvedRegionalCloudPrice | undefined;
    for (const [region, source] of candidates) {
        const amount = Number(source.amount);
        const value =
            (amount * HOUR_MULTIPLIERS[costDuration]) / divisor;
        if (!Number.isFinite(value) || value <= 0) continue;
        if (!result || value < result.value) {
            result = {
                value,
                region,
                source,
                fromMultipleRegions: selectedRegion === "all",
            };
        }
    }
    return result;
}

function formatRegionalCloudPrice(
    price: ResolvedRegionalCloudPrice,
    pricingUnit: PricingUnit,
    costDuration: CostDuration,
): string {
    const amount = Intl.NumberFormat("en-US", {
        style: "currency",
        currency: price.source.currency,
        currencyDisplay: "narrowSymbol",
        maximumFractionDigits: price.value < 0.01 ? 6 : 4,
    }).format(price.value);
    const unit =
        pricingUnit === "instance"
            ? ""
            : pricingUnit === "vcpu"
              ? " / vCPU"
              : pricingUnit === "memory"
                ? " / GiB"
                : "";
    return `${price.fromMultipleRegions ? "From " : ""}${amount} / ${
        DURATION_LABELS[costDuration]
    }${unit}`;
}

const initialColumnsArr = [
    ["familyName", true],
    ["instance_type", true],
    ["family", false],
    ["category", true],
    ["vCPU", true],
    ["memoryGiB", true],
    ["memoryPerVcpu", false],
    ["architecture", true],
    ["processor", true],
    ["networkPerformance", true],
    ["localStorage", true],
    ["pricingUrl", true],
    ["availableZoneCount", false],
    ["regions", false],
    ["zones", false],
] as const;

export const initialColumnsValue: {
    [key in (typeof initialColumnsArr)[number][0]]: boolean;
} = {} as any;
for (const [key, value] of initialColumnsArr) {
    initialColumnsValue[key] = value;
}

export function transformDataTables(dataTablesData: any) {
    return transformAllDataTables(initialColumnsArr, dataTablesData);
}

export function makePrettyNames<V>(
    makeColumnOption: (
        key: keyof typeof initialColumnsValue,
        label: string,
    ) => V,
) {
    return [
        makeColumnOption("familyName", "Name"),
        makeColumnOption("instance_type", "API Name"),
        makeColumnOption("family", "Instance Family"),
        makeColumnOption("category", "Compute Family"),
        makeColumnOption("vCPU", "vCPUs"),
        makeColumnOption("memoryGiB", "Instance Memory"),
        makeColumnOption("memoryPerVcpu", "GiB of Memory per vCPU"),
        makeColumnOption("architecture", "Architecture"),
        makeColumnOption("processor", "Physical Processor"),
        makeColumnOption("networkPerformance", "Network Performance"),
        makeColumnOption("localStorage", "Instance Storage"),
        makeColumnOption("pricingUrl", "Linux On Demand"),
        makeColumnOption("availableZoneCount", "Available Zones"),
        makeColumnOption("regions", "Region IDs"),
        makeColumnOption("zones", "Availability Zone IDs"),
    ];
}

export const columnsGen = (
    selectedRegion: string,
    pricingUnit: PricingUnit,
    costDuration: CostDuration,
    _reservedTerm: string,
    _currency: {
        code: string;
        usdRate: number;
        cnyRate: number;
    },
): ColumnDef<RegionalCloudTableInstance>[] => [
    {
        accessorKey: "familyName",
        header: "Name",
        id: "familyName",
        size: 280,
        sortingFn: "alphanumeric",
        filterFn: regex({ accessorKey: "familyName" }),
    },
    {
        accessorKey: "instance_type",
        header: "API Name",
        id: "instance_type",
        size: 210,
        sortingFn: "alphanumeric",
        filterFn: regex({ accessorKey: "instance_type" }),
        cell: (info) => (
            <span className="font-mono">{info.getValue() as string}</span>
        ),
    },
    {
        accessorKey: "family",
        header: "Instance Family",
        id: "family",
        size: 150,
        sortingFn: "alphanumeric",
        filterFn: regex({ accessorKey: "family" }),
    },
    {
        accessorKey: "category",
        header: "Compute Family",
        id: "category",
        size: 190,
        sortingFn: "alphanumeric",
        filterFn: regex({ accessorKey: "category" }),
    },
    {
        accessorKey: "vCPU",
        header: "vCPUs",
        id: "vCPU",
        size: 100,
        sortingFn: "alphanumeric",
        filterFn: expr,
    },
    {
        accessorKey: "memoryGiB",
        header: "Instance Memory",
        id: "memoryGiB",
        size: 165,
        sortingFn: "alphanumeric",
        filterFn: expr,
        cell: (info) => `${info.getValue() as number} GiB`,
    },
    {
        accessorKey: "memoryPerVcpu",
        header: "Memory / vCPU",
        id: "memoryPerVcpu",
        size: 160,
        sortingFn: "alphanumeric",
        filterFn: expr,
        cell: (info) => `${info.getValue() as number} GiB`,
    },
    {
        accessorKey: "architecture",
        header: "Architecture",
        id: "architecture",
        size: 140,
        sortingFn: "alphanumeric",
        filterFn: regex({ accessorKey: "architecture" }),
    },
    {
        accessorKey: "processor",
        header: "Physical Processor",
        id: "processor",
        size: 260,
        sortingFn: "alphanumeric",
        filterFn: regex({ accessorKey: "processor" }),
    },
    {
        accessorKey: "networkPerformance",
        header: "Network Performance",
        id: "networkPerformance",
        size: 250,
        sortingFn: "alphanumeric",
        filterFn: regex({ accessorKey: "networkPerformance" }),
    },
    {
        accessorKey: "localStorage",
        header: "Instance Storage",
        id: "localStorage",
        size: 190,
        sortingFn: "alphanumeric",
        filterFn: regex({ accessorKey: "localStorage" }),
    },
    {
        accessorFn: (instance) =>
            resolveRegionalCloudPrice(
                instance,
                selectedRegion,
                pricingUnit,
                costDuration,
            )?.value,
        header: "Linux On Demand",
        id: "pricingUrl",
        size: 190,
        enableColumnFilter: false,
        sortingFn: (rowA, rowB, columnId) => {
            const left = rowA.getValue<number | undefined>(columnId);
            const right = rowB.getValue<number | undefined>(columnId);
            if (left === undefined) return right === undefined ? 0 : 1;
            if (right === undefined) return -1;
            return left - right;
        },
        cell: (info) => {
            const instance = info.row.original;
            const price = resolveRegionalCloudPrice(
                instance,
                selectedRegion,
                pricingUnit,
                costDuration,
            );
            const label = price
                ? formatRegionalCloudPrice(
                      price,
                      pricingUnit,
                      costDuration,
                  )
                : "View pricing";
            const title = price
                ? `Public Linux pay-as-you-go price for ${price.region}; excludes account discounts`
                : "No numeric public price was collected for this region";
            return (
                <a
                    href={instance.pricingUrl}
                    target="_blank"
                    rel="noreferrer"
                    title={title}
                    aria-label={`${label} for ${instance.instance_type}`}
                    onClick={(event) => event.stopPropagation()}
                >
                    {label}
                </a>
            );
        },
    },
    {
        accessorKey: "availableZoneCount",
        header: "Available Zones",
        id: "availableZoneCount",
        size: 150,
        sortingFn: "alphanumeric",
        filterFn: expr,
    },
    {
        accessorKey: "regions",
        header: "Region IDs",
        id: "regions",
        size: 300,
        sortingFn: "alphanumeric",
        ...makeCellWithRegexSorter("regions", (info) =>
            info.row.original.regions.join(", "),
        ),
    },
    {
        accessorKey: "zones",
        header: "Availability Zone IDs",
        id: "zones",
        size: 360,
        sortingFn: "alphanumeric",
        ...makeCellWithRegexSorter("zones", (info) =>
            info.row.original.zones.join(", "),
        ),
    },
];
