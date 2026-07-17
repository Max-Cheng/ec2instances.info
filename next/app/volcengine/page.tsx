import RegionalCloudCatalog from "@/components/RegionalCloudCatalog";
import { regionalCloudProviders } from "@/data/regionalClouds";
import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Volcengine ECS Instance Comparison",
    description:
        "Compare Volcengine ECS instance types, processors, vCPUs, memory, architecture, network performance, and regional availability.",
};

export default function VolcenginePage() {
    return (
        <RegionalCloudCatalog provider={regionalCloudProviders.volcengine} />
    );
}
