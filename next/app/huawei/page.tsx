import RegionalCloudCatalog from "@/components/RegionalCloudCatalog";
import { regionalCloudProviders } from "@/data/regionalClouds";
import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Huawei Cloud ECS Instance Comparison",
    description:
        "Compare representative Huawei Cloud ECS flavors, processors, vCPUs, memory, architecture, and network performance.",
};

export default function HuaweiCloudPage() {
    return <RegionalCloudCatalog provider={regionalCloudProviders.huawei} />;
}
