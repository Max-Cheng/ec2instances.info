"use client";

import ColumnFilter from "@/components/ColumnFilter";
import ExportDropdown from "@/components/ExportDropdown";
import FilterDropdown from "@/components/FilterDropdown";
import {
    useColumnVisibility,
    useCompareOn,
    useSearchTerm,
    useSelected,
} from "@/state";
import * as regionalCloudColumns from "@/utils/colunnData/regionalCloud";
import {
    resetGlobalState,
    useGlobalStateValue,
} from "@/utils/useGlobalStateValue";
import { usePathname } from "next/navigation";
import { useMemo } from "react";

export default function RegionalCloudFilters({
    regions,
}: {
    regions: string[];
}) {
    const pathname = usePathname();
    const [columnVisibility, setColumnVisibility] =
        useColumnVisibility(pathname);
    const [searchTerm, setSearchTerm] = useSearchTerm(pathname);
    const [selectedRegion, setSelectedRegion] = useGlobalStateValue(
        "region",
        pathname,
        "all",
    );
    const [compareOn, setCompareOn] = useCompareOn(pathname);
    const [selected] = useSelected(pathname);

    const regionOptions = useMemo(
        () => [
            { value: "all", label: "All regions" },
            ...regions.map((region) => ({
                value: region,
                label: region,
                group: "Available Regions",
            })),
        ],
        [regions],
    );

    const columnOptions = useMemo(
        () =>
            regionalCloudColumns.makePrettyNames((key, label) => ({
                key,
                label,
                visible: columnVisibility[key],
                defaultVisible: regionalCloudColumns.initialColumnsValue[key],
            })),
        [columnVisibility],
    );

    return (
        <div
            className="my-1.5 mx-2 d-flex justify-content-between align-items-end"
            id="menu"
        >
            <div className="d-flex align-items-md-end gap-md-4 gap-4 flex-md-row flex-column">
                <div className="d-flex gap-4">
                    <FilterDropdown
                        label="Region"
                        value={selectedRegion}
                        onChange={setSelectedRegion}
                        options={regionOptions}
                        hideSearch={false}
                        small={true}
                    />
                    <ColumnFilter
                        columns={columnOptions as any}
                        onColumnVisibilityChange={(key, visible) => {
                            setColumnVisibility((old) => ({
                                ...old,
                                [key]: visible,
                            }));
                        }}
                    />
                </div>
                <div className="d-flex gap-2">
                    {compareOn ? (
                        <button
                            className="btn bg-red-600 text-white disabled:opacity-50 self-end"
                            onClick={() => setCompareOn(false)}
                        >
                            End Compare
                        </button>
                    ) : (
                        <button
                            disabled={selected.length === 0}
                            className="btn btn-purple disabled:opacity-50 self-end"
                            onClick={() => setCompareOn(true)}
                        >
                            Compare
                        </button>
                    )}
                    <button
                        className="btn text-sm btn-outline-secondary btn-clear self-end"
                        onClick={() => resetGlobalState(pathname)}
                    >
                        Clear Filters
                    </button>
                </div>
            </div>
            <div className="d-flex gap-2">
                <ExportDropdown />
                <div className="my-auto" id="search">
                    <div className="block">
                        <input
                            id="fullsearch"
                            type="text"
                            className="form-control not-xl:hidden not-2xl:w-25 p-1 border-gray-3 border rounded-md bg-background text-foreground"
                            placeholder="Search..."
                            value={searchTerm}
                            onChange={(event) =>
                                setSearchTerm(event.target.value)
                            }
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}
