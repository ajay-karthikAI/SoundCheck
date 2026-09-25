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
    <Panel className="mt-8 overflow-hidden">
      <PanelHeader
        kicker="Partial coverage"
        title="Known genres not yet eligible for a claim"
        meta={<span className="numeral">{partial.length} withheld</span>}
      />
      <div className="grid sm:grid-cols-2 lg:grid-cols-4">
        {partial.slice(0, limit).map((item) => (
          <Link
            key={item.genre.genre_id}
            href={`/genre/${item.genre.slug}`}
            className="focus-ring group -mb-px -mr-px border-b border-r border-rule px-5 py-4 hover:bg-raised/60"
          >
            <p className="font-serif text-[17px] leading-tight text-ink group-hover:underline group-hover:decoration-rule group-hover:underline-offset-4">
              {item.genre.display_name}
            </p>
            <div className="mt-1.5">
              <CoverageBadge status={item.genre.coverage_status} />
            </div>
            <p className="mt-2 text-[12px] leading-5 text-faint">
              {item.missing_axes.length > 0
                ? `Missing ${item.missing_axes.join(", ")} evidence`
                : "Below the current evidence gate"}
            </p>
          </Link>
        ))}
      </div>
      <p className="border-t border-rule px-5 py-3 text-[13px] leading-5 text-muted sm:px-6">
        These are evidence states, not zero activity. Soundcheck waits until
        the missing source history clears the published gate.
      </p>
    </Panel>
  );
}
