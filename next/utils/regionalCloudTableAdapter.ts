import type { RegionalCloudInstance } from "@/data/regionalClouds";

export type RegionalCloudTableInstance = RegionalCloudInstance & {
    instance_type: string;
    memoryPerVcpu: number;
    pricingUrl: string;
    regions: string[];
    zones: string[];
    availableRegionCount: number;
    availableZoneCount: number;
};

export function adaptRegionalCloudInstance(
    instance: RegionalCloudInstance,
    pricingUrl: string,
): RegionalCloudTableInstance {
    const regions = instance.regions ?? [];
    const zones = instance.zones ?? [];

    return {
        ...instance,
        instance_type: instance.instanceType,
        memoryPerVcpu:
            Math.round((instance.memoryGiB / instance.vCPU) * 100) / 100,
        pricingUrl,
        regions,
        zones,
        availableRegionCount: instance.availableRegionCount ?? regions.length,
        availableZoneCount: instance.availableZoneCount ?? zones.length,
    };
}

export function regionalCloudRegionIds(
    instances: RegionalCloudTableInstance[],
): string[] {
    return [...new Set(instances.flatMap((instance) => instance.regions))].sort(
        (left, right) =>
            left.localeCompare(right, undefined, { numeric: true }),
    );
}
