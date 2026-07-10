import RegionalCloudCatalog from "@/components/RegionalCloudCatalog";
import { regionalCloudProviders } from "@/data/regionalClouds";
import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Volcengine ECS Instance Comparison",
    description:
        "Compare representative Volcengine ECS instance families, processors, vCPUs, memory, architecture, and network performance.",
};

export default function VolcenginePage() {
    return (
        <RegionalCloudCatalog provider={regionalCloudProviders.volcengine} />
    );
}
