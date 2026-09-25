import Link from "next/link";

import {
  CoverageBadge,
  Panel,
  PanelHeader,
} from "@/components/ui";
import { formatInterval, formatNumber } from "@/lib/format";
import type { OpportunityItem } from "@/lib/types";
import { hasOpportunity } from "@/lib/types";
import { palette } from "@/lib/palette";

export function DemandMismatchBoard({
  opportunities,
}: {
  opportunities: OpportunityItem[];
}) {
  const ready = opportunities.filter(hasOpportunity);
  const listeningLed = [...ready]
    .filter((item) => item.discovery_gap.value >= 0)
    .sort((a, b) => b.discovery_gap.value - a.discovery_gap.value);
  const conversationLed = [...ready]
    .filter((item) => item.discovery_gap.value < 0)
    .sort((a, b) => a.discovery_gap.value - b.discovery_gap.value);
  const maximum = Math.max(
    ...ready.map((item) => Math.abs(item.discovery_gap.value)),
    0.001,
  );
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <MismatchPanel
        kicker="Act before the conversation"
        title="Listening is rising quietly"
        color={palette.accent}
        items={listeningLed}
        maximum={maximum}
      />
      <MismatchPanel
        kicker="Validate before investing"
        title="Conversation is ahead of listening"
        color={palette.cool}
        items={conversationLed}
        maximum={maximum}
      />
    </div>
  );
}

function MismatchPanel({
  kicker,
  title,
  color,
  items,
  maximum,
}: {
  kicker: string;
  title: string;
  color: string;
  items: Array<
    OpportunityItem & {
      discovery_gap: NonNullable<OpportunityItem["discovery_gap"]>;
    }
  >;
  maximum: number;
}) {
  return (
    <Panel className="overflow-hidden">
      <PanelHeader
        kicker={kicker}
        title={title}
        meta={
          <span
            className="size-2 rounded-full"
            style={{ background: color }}
          />
        }
      />
      {items.length === 0 ? (
        <p className="px-6 py-16 text-center text-xs text-faint">
          No reliable mismatch appears among the selected peers.
        </p>
      ) : (
        items.map((item, index) => (
          <Link
            key={item.genre.genre_id}
            href={`/genre/${item.genre.slug}?week=${item.week}`}
            className="focus-ring group block border-b hairline px-5 py-5 last:border-0 hover:bg-ink/[0.025]"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex min-w-0 gap-3">
                <span className="numeral text-[10px] text-faint">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <p className="text-[13px] text-ink group-hover:text-ink">
                    {item.genre.display_name}
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <CoverageBadge status={item.genre.coverage_status} />
                    <span className="text-[9px] text-faint">
                      {item.genre.macro_family_name}
                    </span>
                  </div>
                </div>
              </div>
              <div className="text-right">
                <p className="numeral text-sm text-ink">
                  {formatNumber(item.discovery_gap.value)}
                </p>
                <p className="numeral mt-1 text-[9px] text-faint">
                  {formatInterval(item.discovery_gap)}
                </p>
              </div>
            </div>
            <div className="ml-7 mt-4 h-1 overflow-hidden rounded-full bg-ink/[0.05]">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.max(
                    2,
                    (Math.abs(item.discovery_gap.value) / maximum) * 100,
                  )}%`,
                  background: color,
                  opacity: 0.72,
                }}
              />
            </div>
          </Link>
        ))
      )}
    </Panel>
  );
}
