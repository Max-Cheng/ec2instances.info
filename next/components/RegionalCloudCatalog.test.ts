import { expect } from "vitest";
import { fireEvent, RenderResult } from "@testing-library/react";
import componentTests from "@/utils/testing/componentTests";
import { regionalCloudProviders } from "@/data/regionalClouds";
import RegionalCloudCatalog from "./RegionalCloudCatalog";

function getDataRows(component: RenderResult) {
    return component.container.querySelectorAll("tbody tr");
}

componentTests(
    [
        {
            name: "regional cloud catalog filters and compares instances",
            props: { provider: regionalCloudProviders.alibaba },
            test: (component) => {
                expect(getDataRows(component).length).toBe(
                    regionalCloudProviders.alibaba.instances.length,
                );

                const search = component.getByLabelText("Search");
                fireEvent.change(search, { target: { value: "c8i" } });
                expect(getDataRows(component).length).toBe(4);

                fireEvent.change(search, { target: { value: "" } });
                fireEvent.click(
                    component.getByLabelText(
                        "Select ecs.g8i.large for comparison",
                    ),
                );
                fireEvent.click(
                    component.getByLabelText(
                        "Select ecs.g8i.xlarge for comparison",
                    ),
                );

                const compare = component.getByRole("button", {
                    name: "Compare selected (2)",
                });
                expect((compare as HTMLButtonElement).disabled).toBe(false);
                fireEvent.click(compare);
                expect(getDataRows(component).length).toBe(2);
            },
        },
    ],
    RegionalCloudCatalog,
);
