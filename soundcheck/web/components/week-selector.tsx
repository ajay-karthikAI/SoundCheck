"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { formatWeek } from "@/lib/format";

export function WeekSelector({
  availableWeeks,
  selectedWeek,
}: {
  availableWeeks: string[];
  selectedWeek?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const currentSearch = useSearchParams();

  function chooseWeek(week: string) {
    const params = new URLSearchParams(currentSearch.toString());
    if (week) {
      params.set("week", week);
    } else {
      params.delete("week");
    }
    const suffix = params.toString();
    router.push(suffix ? `${pathname}?${suffix}` : pathname);
  }

  return (
    <label className="inline-flex items-baseline gap-2.5 text-[13px]">
      <span aria-hidden="true" className="text-faint">
        Week
      </span>
      <span className="sr-only">Select ISO week</span>
      <select
        value={selectedWeek ?? ""}
        onChange={(event) => chooseWeek(event.target.value)}
        className="select-underline focus-ring numeral text-[13px]"
      >
        <option value="">Latest decision-ready week</option>
        {availableWeeks.map((week) => (
          <option key={week} value={week}>
            Week of {formatWeek(week)}
          </option>
        ))}
      </select>
    </label>
  );
}
