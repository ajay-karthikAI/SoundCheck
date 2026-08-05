"use client";

import { CalendarDays } from "lucide-react";
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
    <label className="flex items-center gap-2">
      <CalendarDays aria-hidden="true" size={13} className="text-white/35" />
      <span className="sr-only">Select ISO week</span>
      <select
        value={selectedWeek ?? ""}
        onChange={(event) => chooseWeek(event.target.value)}
        className="focus-ring numeral rounded-md border hairline bg-surface px-3 py-2 text-[11px] text-white/65 hover:border-white/15"
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
