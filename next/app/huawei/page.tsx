import RegionalCloudIndex from "@/components/RegionalCloudIndex";
import { regionalCloudProviders } from "@/data/regionalClouds";
import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Huawei Cloud ECS Instance Comparison",
    description:
        "Compare Huawei Cloud ECS flavors, processors, vCPUs, memory, architecture, network performance, and regional availability.",
};

export default function HuaweiCloudPage() {
    return <RegionalCloudIndex provider={regionalCloudProviders.huawei} />;
}
