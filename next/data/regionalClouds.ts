import generatedCatalogJson from "./regionalClouds.generated.json";

export const regionalCloudSlugs = [
    "alibaba",
    "tencent",
    "volcengine",
    "huawei",
] as const;

export type RegionalCloudSlug = (typeof regionalCloudSlugs)[number];

export type RegionalCloudCategory =
    | "General purpose"
    | "Compute optimized"
    | "Memory optimized"
    | "Accelerated computing"
    | "Storage optimized"
    | "High performance computing"
    | "Bare metal"
    | "Other";

export type RegionalCloudArchitecture = "x86_64" | "arm64" | "unknown";

export type RegionalCloudInstance = {
    instanceType: string;
    family: string;
    familyName: string;
    category: RegionalCloudCategory;
    vCPU: number;
    memoryGiB: number;
    architecture: RegionalCloudArchitecture;
    processor: string;
    networkPerformance: string;
    localStorage: string;
    sourceUrl: string;
    regions?: string[];
    zones?: string[];
    availableRegionCount?: number;
    availableZoneCount?: number;
};

export type RegionalCloudProvider = {
    slug: RegionalCloudSlug;
    name: string;
    nativeName: string;
    productName: string;
    catalogName: string;
    description: string;
    documentationUrl: string;
    pricingUrl: string;
    lastReviewed: string;
    coverageNote: string;
    generatedAt?: string;
    regionCount?: number;
    zoneCount?: number;
    skippedRegions?: string[];
    dataSource?: "api" | "curated";
    instances: RegionalCloudInstance[];
};

type GeneratedRegionalCloudProvider = {
    slug: RegionalCloudSlug;
    regionCount: number;
    zoneCount: number;
    skippedRegions?: string[];
    instances: RegionalCloudInstance[];
};

type GeneratedRegionalCloudCatalog = {
    schemaVersion: number;
    generatedAt: string | null;
    providers: Partial<
        Record<RegionalCloudSlug, GeneratedRegionalCloudProvider>
    >;
};

type FamilyOptions = Omit<
    RegionalCloudInstance,
    "instanceType" | "vCPU" | "memoryGiB" | "networkPerformance"
> & {
    sizes: readonly {
        name: string;
        vCPU: number;
        memoryGiB: number;
        networkPerformance: string;
    }[];
};

function family(options: FamilyOptions): RegionalCloudInstance[] {
    return options.sizes.map((size) => ({
        instanceType: size.name,
        family: options.family,
        familyName: options.familyName,
        category: options.category,
        vCPU: size.vCPU,
        memoryGiB: size.memoryGiB,
        architecture: options.architecture,
        processor: options.processor,
        networkPerformance: size.networkPerformance,
        localStorage: options.localStorage,
        sourceUrl: options.sourceUrl,
    }));
}

const alibabaGeneralPurposeUrl =
    "https://www.alibabacloud.com/help/en/ecs/user-guide/general-purpose-instance-families";
const alibabaComputeOptimizedUrl =
    "https://www.alibabacloud.com/help/en/ecs/user-guide/compute-optimized-instance-families";
const alibabaMemoryOptimizedUrl =
    "https://www.alibabacloud.com/help/en/ecs/user-guide/memory-optimized-instance-families-1";

const alibabaInstances = [
    ...family({
        family: "g8i",
        familyName: "General-purpose g8i",
        category: "General purpose",
        architecture: "x86_64",
        processor: "Intel Xeon Emerald Rapids or Sapphire Rapids",
        localStorage: "Cloud disks",
        sourceUrl: alibabaGeneralPurposeUrl,
        sizes: [
            {
                name: "ecs.g8i.large",
                vCPU: 2,
                memoryGiB: 8,
                networkPerformance: "2.5 / up to 15 Gbps",
            },
            {
                name: "ecs.g8i.xlarge",
                vCPU: 4,
                memoryGiB: 16,
                networkPerformance: "4 / up to 15 Gbps",
            },
            {
                name: "ecs.g8i.2xlarge",
                vCPU: 8,
                memoryGiB: 32,
                networkPerformance: "6 / up to 15 Gbps",
            },
            {
                name: "ecs.g8i.4xlarge",
                vCPU: 16,
                memoryGiB: 64,
                networkPerformance: "12 / up to 25 Gbps",
            },
        ],
    }),
    ...family({
        family: "g8y",
        familyName: "General-purpose g8y",
        category: "General purpose",
        architecture: "arm64",
        processor: "Alibaba Cloud Yitian 710",
        localStorage: "Cloud disks",
        sourceUrl: alibabaGeneralPurposeUrl,
        sizes: [
            {
                name: "ecs.g8y.large",
                vCPU: 2,
                memoryGiB: 8,
                networkPerformance: "Scales with instance size",
            },
            {
                name: "ecs.g8y.xlarge",
                vCPU: 4,
                memoryGiB: 16,
                networkPerformance: "Scales with instance size",
            },
            {
                name: "ecs.g8y.2xlarge",
                vCPU: 8,
                memoryGiB: 32,
                networkPerformance: "Scales with instance size",
            },
            {
                name: "ecs.g8y.4xlarge",
                vCPU: 16,
                memoryGiB: 64,
                networkPerformance: "Scales with instance size",
            },
        ],
    }),
    ...family({
        family: "c8i",
        familyName: "Compute-optimized c8i",
        category: "Compute optimized",
        architecture: "x86_64",
        processor: "Intel Xeon Emerald Rapids or Sapphire Rapids",
        localStorage: "Cloud disks",
        sourceUrl: alibabaComputeOptimizedUrl,
        sizes: [
            {
                name: "ecs.c8i.large",
                vCPU: 2,
                memoryGiB: 4,
                networkPerformance: "2.5 / up to 15 Gbps",
            },
            {
                name: "ecs.c8i.xlarge",
                vCPU: 4,
                memoryGiB: 8,
                networkPerformance: "4 / up to 15 Gbps",
            },
            {
                name: "ecs.c8i.2xlarge",
                vCPU: 8,
                memoryGiB: 16,
                networkPerformance: "6 / up to 15 Gbps",
            },
            {
                name: "ecs.c8i.4xlarge",
                vCPU: 16,
                memoryGiB: 32,
                networkPerformance: "12 / up to 25 Gbps",
            },
        ],
    }),
    ...family({
        family: "r8i",
        familyName: "Memory-optimized r8i",
        category: "Memory optimized",
        architecture: "x86_64",
        processor: "Intel Xeon Emerald Rapids or Sapphire Rapids",
        localStorage: "Cloud disks",
        sourceUrl: alibabaMemoryOptimizedUrl,
        sizes: [
            {
                name: "ecs.r8i.large",
                vCPU: 2,
                memoryGiB: 16,
                networkPerformance: "2.5 / up to 15 Gbps",
            },
            {
                name: "ecs.r8i.xlarge",
                vCPU: 4,
                memoryGiB: 32,
                networkPerformance: "4 / up to 15 Gbps",
            },
            {
                name: "ecs.r8i.2xlarge",
                vCPU: 8,
                memoryGiB: 64,
                networkPerformance: "6 / up to 15 Gbps",
            },
            {
                name: "ecs.r8i.4xlarge",
                vCPU: 16,
                memoryGiB: 128,
                networkPerformance: "12 / up to 25 Gbps",
            },
        ],
    }),
];

const tencentInstanceSpecificationsUrl =
    "https://intl.cloud.tencent.com/document/product/213/11518";

const tencentInstances = [
    ...family({
        family: "SA5",
        familyName: "Standard SA5",
        category: "General purpose",
        architecture: "x86_64",
        processor: "AMD EPYC Bergamo",
        localStorage: "Cloud Block Storage",
        sourceUrl: tencentInstanceSpecificationsUrl,
        sizes: [
            {
                name: "SA5.MEDIUM4",
                vCPU: 2,
                memoryGiB: 4,
                networkPerformance: "1.5 / 10 Gbps burst",
            },
            {
                name: "SA5.LARGE16",
                vCPU: 4,
                memoryGiB: 16,
                networkPerformance: "1.5 / 10 Gbps burst",
            },
            {
                name: "SA5.2XLARGE32",
                vCPU: 8,
                memoryGiB: 32,
                networkPerformance: "3 / 10 Gbps burst",
            },
            {
                name: "SA5.4XLARGE64",
                vCPU: 16,
                memoryGiB: 64,
                networkPerformance: "5 / 10 Gbps burst",
            },
        ],
    }),
    ...family({
        family: "C6",
        familyName: "Compute Optimized C6",
        category: "Compute optimized",
        architecture: "x86_64",
        processor: "Intel Xeon Ice Lake",
        localStorage: "Cloud Block Storage",
        sourceUrl: tencentInstanceSpecificationsUrl,
        sizes: [
            {
                name: "C6.LARGE8",
                vCPU: 4,
                memoryGiB: 8,
                networkPerformance: "5 Gbps",
            },
            {
                name: "C6.2XLARGE16",
                vCPU: 8,
                memoryGiB: 16,
                networkPerformance: "9 Gbps",
            },
            {
                name: "C6.4XLARGE32",
                vCPU: 16,
                memoryGiB: 32,
                networkPerformance: "18 Gbps",
            },
            {
                name: "C6.8XLARGE128",
                vCPU: 32,
                memoryGiB: 128,
                networkPerformance: "35 Gbps",
            },
        ],
    }),
    ...family({
        family: "M6",
        familyName: "Memory Optimized M6",
        category: "Memory optimized",
        architecture: "x86_64",
        processor: "Intel Xeon, 2.7 GHz",
        localStorage: "Cloud Block Storage",
        sourceUrl: tencentInstanceSpecificationsUrl,
        sizes: [
            {
                name: "M6.MEDIUM16",
                vCPU: 2,
                memoryGiB: 16,
                networkPerformance: "2 Gbps",
            },
            {
                name: "M6.LARGE32",
                vCPU: 4,
                memoryGiB: 32,
                networkPerformance: "4 Gbps",
            },
            {
                name: "M6.2XLARGE64",
                vCPU: 8,
                memoryGiB: 64,
                networkPerformance: "7 Gbps",
            },
            {
                name: "M6.4XLARGE128",
                vCPU: 16,
                memoryGiB: 128,
                networkPerformance: "13 Gbps",
            },
        ],
    }),
];

const volcengineInstanceTypesUrl =
    "https://api.volcengine.com/api-docs/view?action=DescribeInstanceTypes&serviceCode=ecs&version=2020-04-01";

const volcengineInstances = [
    ...family({
        family: "g3i",
        familyName: "General-purpose g3i",
        category: "General purpose",
        architecture: "x86_64",
        processor: "Intel Xeon",
        localStorage: "Cloud volumes",
        sourceUrl: volcengineInstanceTypesUrl,
        sizes: [
            {
                name: "ecs.g3i.large",
                vCPU: 2,
                memoryGiB: 8,
                networkPerformance: "Scales with size; family up to 96 Gbps",
            },
            {
                name: "ecs.g3i.xlarge",
                vCPU: 4,
                memoryGiB: 16,
                networkPerformance: "Scales with size; family up to 96 Gbps",
            },
            {
                name: "ecs.g3i.2xlarge",
                vCPU: 8,
                memoryGiB: 32,
                networkPerformance: "Scales with size; family up to 96 Gbps",
            },
            {
                name: "ecs.g3i.4xlarge",
                vCPU: 16,
                memoryGiB: 64,
                networkPerformance: "Scales with size; family up to 96 Gbps",
            },
        ],
    }),
    ...family({
        family: "c3i",
        familyName: "Compute-optimized c3i",
        category: "Compute optimized",
        architecture: "x86_64",
        processor: "Intel Xeon",
        localStorage: "Cloud volumes",
        sourceUrl: volcengineInstanceTypesUrl,
        sizes: [
            {
                name: "ecs.c3i.large",
                vCPU: 2,
                memoryGiB: 4,
                networkPerformance: "2.5 / up to 12 Gbps",
            },
            {
                name: "ecs.c3i.xlarge",
                vCPU: 4,
                memoryGiB: 8,
                networkPerformance: "4 / up to 12 Gbps",
            },
            {
                name: "ecs.c3i.2xlarge",
                vCPU: 8,
                memoryGiB: 16,
                networkPerformance: "Scales with instance size",
            },
            {
                name: "ecs.c3i.4xlarge",
                vCPU: 16,
                memoryGiB: 32,
                networkPerformance: "Scales with instance size",
            },
        ],
    }),
    ...family({
        family: "r3i",
        familyName: "Memory-optimized r3i",
        category: "Memory optimized",
        architecture: "x86_64",
        processor: "Intel Xeon",
        localStorage: "Cloud volumes",
        sourceUrl: volcengineInstanceTypesUrl,
        sizes: [
            {
                name: "ecs.r3i.large",
                vCPU: 2,
                memoryGiB: 16,
                networkPerformance: "Scales with size; family up to 96 Gbps",
            },
            {
                name: "ecs.r3i.xlarge",
                vCPU: 4,
                memoryGiB: 32,
                networkPerformance: "Scales with size; family up to 96 Gbps",
            },
            {
                name: "ecs.r3i.2xlarge",
                vCPU: 8,
                memoryGiB: 64,
                networkPerformance: "Scales with size; family up to 96 Gbps",
            },
            {
                name: "ecs.r3i.4xlarge",
                vCPU: 16,
                memoryGiB: 128,
                networkPerformance: "Scales with size; family up to 96 Gbps",
            },
        ],
    }),
];

const huaweiGeneralComputeUrl =
    "https://support.huaweicloud.com/intl/en-us/productdesc-ecs/en-us_topic_0086381982.html";
const huaweiMemoryOptimizedUrl =
    "https://support.huaweicloud.com/intl/en-us/productdesc-ecs/ecs_01_0031.html";

const huaweiInstances = [
    ...family({
        family: "aC7",
        familyName: "General Computing-plus aC7",
        category: "General purpose",
        architecture: "x86_64",
        processor: "AMD scalable processor",
        localStorage: "EVS cloud disks",
        sourceUrl: huaweiGeneralComputeUrl,
        sizes: [
            {
                name: "ac7.large.2",
                vCPU: 2,
                memoryGiB: 4,
                networkPerformance: "2 / 1 Gbps max/assured",
            },
            {
                name: "ac7.xlarge.2",
                vCPU: 4,
                memoryGiB: 8,
                networkPerformance: "3 / 1.5 Gbps max/assured",
            },
            {
                name: "ac7.2xlarge.2",
                vCPU: 8,
                memoryGiB: 16,
                networkPerformance: "4 / 2.5 Gbps max/assured",
            },
            {
                name: "ac7.4xlarge.2",
                vCPU: 16,
                memoryGiB: 32,
                networkPerformance: "8 / 5 Gbps max/assured",
            },
        ],
    }),
    ...family({
        family: "C7e",
        familyName: "General Computing-plus C7e",
        category: "Compute optimized",
        architecture: "x86_64",
        processor: "Intel Xeon Scalable",
        localStorage: "EVS cloud disks",
        sourceUrl: huaweiGeneralComputeUrl,
        sizes: [
            {
                name: "c7e.large.4",
                vCPU: 2,
                memoryGiB: 8,
                networkPerformance: "10 / 1.6 Gbps max/assured",
            },
            {
                name: "c7e.xlarge.4",
                vCPU: 4,
                memoryGiB: 16,
                networkPerformance: "16 / 3 Gbps max/assured",
            },
            {
                name: "c7e.2xlarge.4",
                vCPU: 8,
                memoryGiB: 32,
                networkPerformance: "20 / 6 Gbps max/assured",
            },
            {
                name: "c7e.4xlarge.4",
                vCPU: 16,
                memoryGiB: 64,
                networkPerformance: "40 / 13 Gbps max/assured",
            },
        ],
    }),
    ...family({
        family: "M7",
        familyName: "Memory-optimized M7",
        category: "Memory optimized",
        architecture: "x86_64",
        processor: "Intel Xeon Scalable",
        localStorage: "EVS cloud disks",
        sourceUrl: huaweiMemoryOptimizedUrl,
        sizes: [
            {
                name: "m7.large.8",
                vCPU: 2,
                memoryGiB: 16,
                networkPerformance: "4 / 0.8 Gbps max/assured",
            },
            {
                name: "m7.xlarge.8",
                vCPU: 4,
                memoryGiB: 32,
                networkPerformance: "8 / 1.6 Gbps max/assured",
            },
            {
                name: "m7.2xlarge.8",
                vCPU: 8,
                memoryGiB: 64,
                networkPerformance: "15 / 3 Gbps max/assured",
            },
            {
                name: "m7.4xlarge.8",
                vCPU: 16,
                memoryGiB: 128,
                networkPerformance: "20 / 6 Gbps max/assured",
            },
        ],
    }),
];

const curatedRegionalCloudProviders: Record<
    RegionalCloudSlug,
    RegionalCloudProvider
> = {
    alibaba: {
        slug: "alibaba",
        name: "Alibaba Cloud",
        nativeName: "阿里云",
        productName: "Elastic Compute Service (ECS)",
        catalogName: "Alibaba Cloud ECS",
        description:
            "Compare Alibaba Cloud ECS general-purpose, compute-optimized, memory-optimized, Arm, storage, and accelerated instance types.",
        documentationUrl:
            "https://www.alibabacloud.com/help/en/ecs/user-guide/instance-families/",
        pricingUrl: "https://www.alibabacloud.com/pricing/calculator",
        lastReviewed: "2026-07-10",
        coverageNote:
            "Representative current-generation families. Availability and assigned processor can vary by region.",
        instances: alibabaInstances,
    },
    tencent: {
        slug: "tencent",
        name: "Tencent Cloud",
        nativeName: "腾讯云",
        productName: "Cloud Virtual Machine (CVM)",
        catalogName: "Tencent Cloud CVM",
        description:
            "Compare Tencent Cloud CVM standard, compute-optimized, memory-optimized, storage, and accelerated instance types.",
        documentationUrl: tencentInstanceSpecificationsUrl,
        pricingUrl: "https://buy.cloud.tencent.com/price/cvm/calculator",
        lastReviewed: "2026-07-10",
        coverageNote:
            "Representative families from the international specification catalog. Availability varies by region and account.",
        instances: tencentInstances,
    },
    volcengine: {
        slug: "volcengine",
        name: "Volcengine",
        nativeName: "火山引擎",
        productName: "Elastic Compute Service (ECS)",
        catalogName: "Volcengine ECS",
        description:
            "Compare Volcengine ECS general-purpose, compute-optimized, memory-optimized, storage, and accelerated instance types.",
        documentationUrl: volcengineInstanceTypesUrl,
        pricingUrl: "https://www.volcengine.com/pricing",
        lastReviewed: "2026-07-10",
        coverageNote:
            "Representative third-generation families. Exact network limits and availability vary by size and region.",
        instances: volcengineInstances,
    },
    huawei: {
        slug: "huawei",
        name: "Huawei Cloud",
        nativeName: "华为云",
        productName: "Elastic Cloud Server (ECS)",
        catalogName: "Huawei Cloud ECS",
        description:
            "Compare Huawei Cloud ECS general computing-plus, compute-optimized, memory-optimized, storage, and accelerated flavors.",
        documentationUrl:
            "https://support.huaweicloud.com/intl/en-us/productdesc-ecs/en-us_topic_0035470096.html",
        pricingUrl: "https://www.huaweicloud.com/intl/en-us/pricing/index.html",
        lastReviewed: "2026-07-10",
        coverageNote:
            "Representative x86 QingTian and KVM flavors. Flavor availability differs across Huawei Cloud regions.",
        instances: huaweiInstances,
    },
};

const generatedCatalog =
    generatedCatalogJson as unknown as GeneratedRegionalCloudCatalog;

function resolveProvider(slug: RegionalCloudSlug): RegionalCloudProvider {
    const curated = curatedRegionalCloudProviders[slug];
    const generated = generatedCatalog.providers[slug];
    if (
        !generatedCatalog.generatedAt ||
        !generated ||
        generated.instances.length === 0
    ) {
        return {
            ...curated,
            dataSource: "curated",
            regionCount: 0,
            zoneCount: 0,
        };
    }

    return {
        ...curated,
        dataSource: "api",
        generatedAt: generatedCatalog.generatedAt,
        lastReviewed: generatedCatalog.generatedAt.slice(0, 10),
        regionCount: generated.regionCount,
        zoneCount: generated.zoneCount,
        skippedRegions: generated.skippedRegions ?? [],
        coverageNote: `Live API snapshot across ${generated.regionCount} regions and ${generated.zoneCount} availability zones.${
            generated.skippedRegions?.length
                ? ` ${generated.skippedRegions.length} account-inaccessible regions were skipped.`
                : ""
        }`,
        instances: generated.instances,
    };
}

export const regionalCloudProviders = Object.fromEntries(
    regionalCloudSlugs.map((slug) => [slug, resolveProvider(slug)]),
) as Record<RegionalCloudSlug, RegionalCloudProvider>;
