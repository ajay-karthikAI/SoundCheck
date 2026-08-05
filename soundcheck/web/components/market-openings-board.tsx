"use client";

import { ArrowUpRight, Sparkles } from "lucide-react";
import Link from "next/link";
import {
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import {
  BandValue,
  CoverageBadge,
  Panel,
  PanelHeader,
} from "@/components/ui";
import {
  formatCompact,
  formatInterval,
  formatNumber,
  gapColor,
} from "@/lib/format";
import type {
  EstimateBand,
  OpportunityItem,
  SceneMapPoint,
} from "@/lib/types";
import { hasOpportunity } from "@/lib/types";

type DecisionPoint = {
  genreId: string;
  slug: string;
  label: string;
  family: string;
  releasePressure: number;
  plottedReleasePressure: number;
  audienceDemand: number;
  evidenceVolume: number;
  discoveryGap: EstimateBand;
  opportunity: EstimateBand;
  demand: EstimateBand;
  supply: EstimateBand;
  effectiveN: string;
  shrinkage: string;
  breakout: boolean;
};

const MAX_BEESWARM_LANES = 13;

function spreadTiedSupplyScores(
  points: Array<Omit<DecisionPoint, "plottedReleasePressure">>,
): DecisionPoint[] {
  const levels = [...new Set(points.map((point) => point.releasePressure))].sort(
    (left, right) => left - right,
  );
  const gaps = levels
    .slice(1)
    .map((level, index) => level - (levels[index] ?? level));
  const smallestGap = gaps.length > 0 ? Math.min(...gaps) : 1;
  const maximumOffset = Math.min(0.36, smallestGap * 0.24);
  const offsetsByGenre = new Map<string, number>();

  levels.forEach((level) => {
    const tied = points
      .filter((point) => point.releasePressure === level)
      .sort(
        (left, right) =>
          left.audienceDemand - right.audienceDemand ||
          left.genreId.localeCompare(right.genreId),
      );
    const laneCount = Math.min(tied.length, MAX_BEESWARM_LANES);
    const furthestLane = Math.ceil((laneCount - 1) / 2);
    const laneStep = furthestLane > 0 ? maximumOffset / furthestLane : 0;

    tied.forEach((point, index) => {
      const lanePosition = index % laneCount;
      const lane =
        lanePosition === 0
          ? 0
          : Math.ceil(lanePosition / 2) *
            (lanePosition % 2 === 1 ? -1 : 1);
      offsetsByGenre.set(point.genreId, lane * laneStep);
    });
  });

  return points.map((point) => ({
    ...point,
    plottedReleasePressure:
      point.releasePressure + (offsetsByGenre.get(point.genreId) ?? 0),
  }));
}

export function MarketOpeningsBoard({
  opportunities,
  sceneContext,
}: {
  opportunities: OpportunityItem[];
  sceneContext: SceneMapPoint[];
}) {
  const ready = opportunities.filter(hasOpportunity);
  const volumeByGenre = new Map(
    sceneContext.map((point) => [
      point.genre.genre_id,
      point.evidence_volume,
    ]),
  );
  const points = spreadTiedSupplyScores(
    ready.map((item) => {
      const demand = {
        value: (item.conversation.value + item.listening.value) / 2,
        lower: (item.conversation.lower + item.listening.lower) / 2,
        upper: (item.conversation.upper + item.listening.upper) / 2,
      };
      return {
        genreId: item.genre.genre_id,
        slug: item.genre.slug,
        label: item.genre.display_name,
        family: item.genre.macro_family_name,
        releasePressure: item.supply.value,
        audienceDemand: demand.value,
        evidenceVolume: volumeByGenre.get(item.genre.genre_id) ?? 1,
        discoveryGap: item.discovery_gap,
        opportunity: item.opportunity,
        demand,
        supply: item.supply,
        effectiveN: [
        item.diagnostics.conversation_effective_n,
        item.diagnostics.listening_effective_n,
        item.diagnostics.supply_effective_n,
      ]
        .map((value) =>
          value === null ? "—" : formatNumber(value, 1),
        )
        .join(" / "),
        shrinkage: [
        item.diagnostics.conversation_shrinkage_weight,
        item.diagnostics.listening_shrinkage_weight,
        item.diagnostics.supply_shrinkage_weight,
      ]
        .map((value) =>
          value === null ? "—" : formatNumber(value, 2),
        )
        .join(" / "),
        breakout: item.breakout_flag === true,
      };
    }),
  );
  const releasePressureLevels = [
    ...new Set(points.map((point) => point.releasePressure)),
  ].sort((left, right) => left - right);
  const plottedReleasePressures = points.map(
    (point) => point.plottedReleasePressure,
  );
  const releasePressureDomain: [number, number] =
    plottedReleasePressures.length > 0
      ? [
          Math.min(...plottedReleasePressures) - 0.2,
          Math.max(...plottedReleasePressures) + 0.2,
        ]
      : [-1, 1];

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(340px,.8fr)]">
      <Panel>
        <PanelHeader
          kicker="Compare like with like"
          title="Audience demand versus release pressure"
          meta={
            <span className="numeral text-[9px] text-white/28">
              size = evidence · color = discovery gap
            </span>
          }
        />
        <div className="relative h-[510px] px-2 pb-3 pt-7 sm:px-4">
          <div className="pointer-events-none absolute inset-x-16 top-7 z-10 flex justify-between text-[9px] uppercase tracking-[0.14em] text-white/18">
            <span>Underserved</span>
            <span>Hot & crowded</span>
          </div>
          <div className="pointer-events-none absolute inset-x-16 bottom-12 z-10 flex justify-between text-[9px] uppercase tracking-[0.14em] text-white/18">
            <span>Quiet</span>
            <span>Saturated</span>
          </div>
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 16, right: 18, bottom: 24, left: 10 }}>
              <CartesianGrid
                className="chart-grid"
                strokeDasharray="2 8"
                vertical={false}
              />
              <XAxis
                type="number"
                dataKey="plottedReleasePressure"
                domain={releasePressureDomain}
                ticks={releasePressureLevels}
                tickFormatter={(value: number) => formatNumber(value, 1)}
                tickLine={false}
                axisLine={{ stroke: "rgba(255,255,255,.08)" }}
                label={{
                  value: "RELEASE SUPPLY →",
                  position: "insideBottomRight",
                  offset: -12,
                  fill: "#55555d",
                  fontSize: 9,
                }}
              />
              <YAxis
                type="number"
                dataKey="audienceDemand"
                tickLine={false}
                axisLine={{ stroke: "rgba(255,255,255,.08)" }}
                label={{
                  value: "ATTENTION",
                  angle: -90,
                  position: "insideLeft",
                  fill: "#55555d",
                  fontSize: 9,
                }}
              />
              <ZAxis type="number" dataKey="evidenceVolume" range={[18, 96]} />
              <ReferenceLine
                x={0}
                stroke="#d6ad54"
                strokeOpacity={0.82}
                strokeWidth={1.5}
                label={{
                  value: "SUPPLY = 0",
                  position: "insideTopLeft",
                  fill: "#d6ad54",
                  fontSize: 8,
                }}
              />
              <ReferenceLine
                y={0}
                stroke="#d6ad54"
                strokeOpacity={0.82}
                strokeWidth={1.5}
                label={{
                  value: "DEMAND = 0",
                  position: "insideTopRight",
                  fill: "#d6ad54",
                  fontSize: 8,
                }}
              />
              <Tooltip
                cursor={{ stroke: "rgba(255,255,255,.10)" }}
                content={({ active, payload }) => {
                  const point = payload?.[0]?.payload as
                    | DecisionPoint
                    | undefined;
                  return active && point ? (
                    <OpeningTooltip point={point} />
                  ) : null;
                }}
              />
              <Scatter data={points} isAnimationActive={false}>
                {points.map((point) => (
                  <Cell
                    key={point.genreId}
                    fill={gapColor(point.discoveryGap.value)}
                    fillOpacity={0.78}
                    stroke="rgba(255,255,255,.42)"
                    strokeWidth={0.55}
                    className="chart-dot"
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t hairline px-5 py-3 text-[10px] text-white/30">
          <span>Horizontal spread separates tied supply scores</span>
          <span>Tooltip retains exact supply · color = discovery gap</span>
        </div>
      </Panel>

      <Panel className="overflow-hidden">
        <PanelHeader
          kicker="Decide what to investigate"
          title="Ranked openings"
          meta={
            <span className="numeral text-[9px] text-white/28">
              score · 90% range
            </span>
          }
        />
        <div className="max-h-[566px] overflow-y-auto">
          {ready.map((item, index) => (
            <OpeningRow
              key={item.genre.genre_id}
              item={item}
              rank={index + 1}
            />
          ))}
        </div>
      </Panel>
    </div>
  );
}

function OpeningTooltip({ point }: { point: DecisionPoint }) {
  return (
    <div className="w-72 rounded-md border border-white/10 bg-[#111114] p-4 text-xs">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-medium">{point.label}</p>
          <p className="mt-1 text-[9px] text-white/30">{point.family}</p>
        </div>
        {point.breakout ? (
          <span className="numeral text-[9px] text-accent">breakout</span>
        ) : null}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 border-y hairline py-4">
        <TooltipBand label="Opportunity" band={point.opportunity} />
        <TooltipBand label="Discovery gap" band={point.discoveryGap} />
        <TooltipBand label="Attention" band={point.demand} />
        <TooltipBand label="Release supply" band={point.supply} />
      </div>
      <div className="mt-3 grid gap-2 text-[9px] text-white/35">
        <p>
          Evidence records{" "}
          <span className="numeral text-white/65">
            {formatCompact(point.evidenceVolume)}
          </span>
        </p>
        <p>
          effective n · conversation / listening / supply{" "}
          <span className="numeral text-white/65">{point.effectiveN}</span>
        </p>
        <p>
          shrinkage · conversation / listening / supply{" "}
          <span className="numeral text-white/65">{point.shrinkage}</span>
        </p>
      </div>
    </div>
  );
}

function TooltipBand({
  label,
  band,
}: {
  label: string;
  band: EstimateBand;
}) {
  return (
    <div>
      <p className="text-[9px] uppercase tracking-[0.1em] text-white/28">
        {label}
      </p>
      <p className="numeral mt-1 text-sm text-white/80">
        {formatNumber(band.value)}
      </p>
      <p className="numeral mt-1 text-[9px] text-white/28">
        {formatInterval(band)}
      </p>
    </div>
  );
}

function OpeningRow({
  item,
  rank,
}: {
  item: OpportunityItem & {
    opportunity: EstimateBand;
    discovery_gap: EstimateBand;
  };
  rank: number;
}) {
  return (
    <Link
      href={`/genre/${item.genre.slug}?week=${item.week}`}
      className="focus-ring group block border-b hairline px-5 py-4 last:border-0 hover:bg-white/[0.025]"
    >
      <div className="flex items-start gap-3">
        <span className="numeral w-5 pt-0.5 text-[10px] text-white/22">
          {String(rank).padStart(2, "0")}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[13px] text-white/78 group-hover:text-white">
                {item.genre.display_name}
              </p>
              <div className="mt-2 flex items-center gap-2">
                <CoverageBadge status={item.genre.coverage_status} />
                <span className="text-[9px] text-white/25">
                  {item.genre.macro_family_name}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {item.breakout_flag ? (
                <Sparkles size={11} className="text-accent" />
              ) : null}
              <BandValue band={item.opportunity} />
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between text-[9px] text-white/25">
            <span className="numeral">
              gap {formatNumber(item.discovery_gap.value)} ·{" "}
              {formatInterval(item.discovery_gap)}
            </span>
            <ArrowUpRight
              size={11}
              className="opacity-0 group-hover:opacity-100"
            />
          </div>
        </div>
      </div>
    </Link>
  );
}
