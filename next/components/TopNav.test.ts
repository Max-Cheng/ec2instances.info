import { afterAll, expect, vi } from "vitest";
import componentTests from "@/utils/testing/componentTests";
import TopNav from "./TopNav";
import { RenderResult } from "@testing-library/react";

const AWS_PATHS = ["/", "/rds", "/cache", "/redshift", "/opensearch"];
const CHINA_CLOUD_PATHS = ["/alibaba", "/tencent", "/volcengine", "/huawei"];

function runSelectedTest(pathLitUp: string) {
    return (component: RenderResult) => {
        const currents =
            component.container.querySelectorAll("a[aria-current]");
        const formatted = Array.from(currents).map((c) => ({
            label: c.textContent,
            href: c.getAttribute("href"),
            ariaCurrent: c.getAttribute("aria-current") === "true",
        }));
        const expected = [
            {
                label: "AWS",
                href: "/",
                ariaCurrent: AWS_PATHS.includes(pathLitUp),
            },
            {
                label: "EC2",
                href: "/",
                ariaCurrent: pathLitUp === "/",
            },
            {
                label: "RDS",
                href: "/rds",
                ariaCurrent: pathLitUp === "/rds",
            },
            {
                label: "ElastiCache",
                href: "/cache",
                ariaCurrent: pathLitUp === "/cache",
            },
            {
                label: "Redshift",
                href: "/redshift",
                ariaCurrent: pathLitUp === "/redshift",
            },
            {
                label: "OpenSearch",
                href: "/opensearch",
                ariaCurrent: pathLitUp === "/opensearch",
            },
            {
                label: "Azure",
                href: "/azure",
                ariaCurrent: pathLitUp === "/azure",
            },
            {
                label: "GCP",
                href: "/gcp",
                ariaCurrent: pathLitUp === "/gcp",
            },
            {
                label: "China Clouds",
                href: "/alibaba",
                ariaCurrent: CHINA_CLOUD_PATHS.includes(pathLitUp),
            },
            {
                label: "Alibaba Cloud",
                href: "/alibaba",
                ariaCurrent: pathLitUp === "/alibaba",
            },
            {
                label: "Tencent Cloud",
                href: "/tencent",
                ariaCurrent: pathLitUp === "/tencent",
            },
            {
                label: "Volcengine",
                href: "/volcengine",
                ariaCurrent: pathLitUp === "/volcengine",
            },
            {
                label: "Huawei Cloud",
                href: "/huawei",
                ariaCurrent: pathLitUp === "/huawei",
            },
        ];
        expect(formatted).toEqual(expected);
    };
}

const mockNavigation = vi.hoisted(() => ({ path: "/" }));

vi.mock("next/navigation", () => ({
    usePathname: vi.fn().mockImplementation(() => mockNavigation.path),
}));

afterAll(() => {
    vi.clearAllMocks();
});

componentTests(
    [
        // EC2

        {
            name: "root path lights up EC2",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/";
                },
            },
            test: runSelectedTest("/"),
        },
        {
            name: "EC2 instance lights up EC2",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/aws/ec2/123";
                },
            },
            test: runSelectedTest("/"),
        },

        // RDS

        {
            name: "RDS lights up RDS when on table page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/rds";
                },
            },
            test: runSelectedTest("/rds"),
        },
        {
            name: "RDS lights up RDS when on instance page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/aws/rds/123";
                },
            },
            test: runSelectedTest("/rds"),
        },

        // ElastiCache

        {
            name: "ElastiCache lights up ElastiCache when on table page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/cache";
                },
            },
            test: runSelectedTest("/cache"),
        },
        {
            name: "ElastiCache lights up ElastiCache when on instance page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/aws/elasticache/123";
                },
            },
            test: runSelectedTest("/cache"),
        },

        // Redshift

        {
            name: "Redshift lights up Redshift when on table page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/redshift";
                },
            },
            test: runSelectedTest("/redshift"),
        },
        {
            name: "Redshift lights up Redshift when on instance page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/aws/redshift/123";
                },
            },
            test: runSelectedTest("/redshift"),
        },

        // OpenSearch

        {
            name: "OpenSearch lights up OpenSearch when on table page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/opensearch";
                },
            },
            test: runSelectedTest("/opensearch"),
        },
        {
            name: "OpenSearch lights up OpenSearch when on instance page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/aws/opensearch/123";
                },
            },
            test: runSelectedTest("/opensearch"),
        },

        // Azure

        {
            name: "Azure lights up Azure when on table page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/azure";
                },
            },
            test: runSelectedTest("/azure"),
        },
        {
            name: "Azure lights up Azure when on instance page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/azure/vm/123";
                },
            },
            test: runSelectedTest("/azure"),
        },

        // GCP

        {
            name: "GCP lights up GCP when on table page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/gcp";
                },
            },
            test: runSelectedTest("/gcp"),
        },
        {
            name: "GCP lights up GCP when on instance page",
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = "/gcp/123";
                },
            },
            test: runSelectedTest("/gcp"),
        },

        // China clouds

        ...CHINA_CLOUD_PATHS.map((path) => ({
            name: `${path} lights up its China cloud navigation item`,
            props: {},
            patch: {
                before: () => {
                    mockNavigation.path = path;
                },
            },
            test: runSelectedTest(path),
        })),
    ],
    TopNav,
);
