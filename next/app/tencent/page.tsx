import RegionalCloudIndex from "@/components/RegionalCloudIndex";
import { regionalCloudProviders } from "@/data/regionalClouds";
import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Tencent Cloud CVM Instance Comparison",
    description:
        "Compare Tencent Cloud CVM instance types, processors, vCPUs, memory, architecture, network performance, and regional availability.",
};

export default function TencentCloudPage() {
    return <RegionalCloudIndex provider={regionalCloudProviders.tencent} />;
}
