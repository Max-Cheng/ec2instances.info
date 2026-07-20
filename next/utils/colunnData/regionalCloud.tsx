import type { CostDuration, PricingUnit } from "@/types";
import type { RegionalCloudTableInstance } from "@/utils/regionalCloudTableAdapter";
import type { ColumnDef } from "@tanstack/react-table";
import {
    expr,
    makeCellWithRegexSorter,
    regex,
    transformAllDataTables,
} from "./shared";

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
        makeColumnOption("pricingUrl", "Pricing"),
        makeColumnOption("availableZoneCount", "Available Zones"),
        makeColumnOption("regions", "Region IDs"),
        makeColumnOption("zones", "Availability Zone IDs"),
    ];
}

export const columnsGen = (
    _selectedRegion: string,
    _pricingUnit: PricingUnit,
    _costDuration: CostDuration,
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
        accessorKey: "pricingUrl",
        header: "Pricing",
        id: "pricingUrl",
        size: 140,
        enableColumnFilter: false,
        enableSorting: false,
        cell: (info) => (
            <a
                href={info.getValue() as string}
                target="_blank"
                rel="noreferrer"
                aria-label={`View ${info.row.original.instance_type} pricing`}
                onClick={(event) => event.stopPropagation()}
            >
                View pricing
            </a>
        ),
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
