import Link from "next/link";

import {
  CoverageBadge,
  Panel,
  PanelHeader,
} from "@/components/ui";
import type { CoverageItem } from "@/lib/types";

export function CoverageSummary({
  coverage,
  limit = 8,
}: {
  coverage: CoverageItem[];
  limit?: number;
}) {
  const partial = coverage.filter(
    (item) => item.genre.coverage_status !== "ready",
  );
  if (partial.length === 0) return null;
  return (
    <Panel className="mt-6 overflow-hidden">
      <PanelHeader
        kicker="Partial coverage"
        title="Known genres not yet eligible for a claim"
        meta={
          <span className="numeral text-[9px] text-white/28">
            {partial.length} withheld
          </span>
        }
      />
      <div className="grid sm:grid-cols-2 lg:grid-cols-4">
        {partial.slice(0, limit).map((item) => (
          <Link
            key={item.genre.genre_id}
            href={`/genre/${item.genre.slug}`}
            className="focus-ring border-b border-r hairline px-4 py-4 hover:bg-white/[0.025]"
          >
            <p className="text-xs text-white/65">
              {item.genre.display_name}
            </p>
            <div className="mt-2">
              <CoverageBadge status={item.genre.coverage_status} />
            </div>
            <p className="mt-3 text-[9px] leading-4 text-white/27">
              {item.missing_axes.length > 0
                ? `Missing ${item.missing_axes.join(", ")} evidence`
                : "Below the current evidence gate"}
            </p>
          </Link>
        ))}
      </div>
      <p className="border-t hairline px-5 py-3 text-[10px] leading-4 text-white/30">
        These are evidence states, not zero activity. Soundcheck waits until
        the missing source history clears the published gate.
      </p>
    </Panel>
  );
}
