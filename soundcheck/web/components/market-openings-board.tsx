"use client";

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
import { palette } from "@/lib/palette";
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
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(340px,.8fr)]">
      <Panel>
        <PanelHeader
          kicker="Compare like with like"
          title="Audience demand versus release pressure"
          meta={
            <span>
              Dot size: evidence
              <br />
              Color: discovery gap
            </span>
          }
        />
        <div className="relative h-[510px] px-2 pb-3 pt-7 sm:px-4">
          <div className="pointer-events-none absolute left-28 right-10 top-14 z-10 flex justify-between font-serif text-[14px] italic text-faint">
            <span>Underserved</span>
            <span>Hot &amp; crowded</span>
          </div>
          <div className="pointer-events-none absolute bottom-[88px] left-28 right-10 z-10 flex justify-between font-serif text-[14px] italic text-faint">
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
                axisLine={{ stroke: palette.rule }}
                label={{
                  value: "Release supply →",
                  position: "insideBottomRight",
                  offset: -12,
                  fill: palette.muted,
                  fontSize: 12,
                }}
              />
              <YAxis
                type="number"
                dataKey="audienceDemand"
                tickFormatter={(value: number) => formatNumber(value, 2)}
                tickLine={false}
                axisLine={{ stroke: palette.rule }}
                label={{
                  value: "Attention",
                  angle: -90,
                  position: "insideLeft",
                  fill: palette.muted,
                  fontSize: 12,
                }}
              />
              <ZAxis type="number" dataKey="evidenceVolume" range={[24, 140]} />
              <ReferenceLine
                x={0}
                stroke={palette.ink}
                strokeDasharray="4 4"
                strokeWidth={1}
                label={{
                  value: "Supply = 0",
                  position: "insideTopLeft",
                  fill: palette.muted,
                  fontSize: 11,
                }}
              />
              <ReferenceLine
                y={0}
                stroke={palette.ink}
                strokeDasharray="4 4"
                strokeWidth={1}
                label={{
                  value: "Demand = 0",
                  position: "insideTopRight",
                  fill: palette.muted,
                  fontSize: 11,
                }}
              />
              <Tooltip
                cursor={{ stroke: palette.rule }}
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
                    fillOpacity={0.9}
                    stroke={palette.surface}
                    strokeWidth={1.5}
                    className="chart-dot"
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-t border-rule px-5 py-3 text-[12px] text-faint sm:px-6">
          <span className="inline-flex flex-wrap items-center gap-x-4 gap-y-1">
            <LegendSwatch color={palette.accent} label="Gap above +0.35" />
            <LegendSwatch color={palette.neutral} label="Near zero" />
            <LegendSwatch color={palette.cool} label="Below −0.35" />
          </span>
          <span>
            Tied supply scores are spread horizontally; the tooltip keeps the
            exact value.
          </span>
        </div>
      </Panel>

      <Panel className="overflow-hidden">
        <PanelHeader
          kicker="Decide what to investigate"
          title="Ranked openings"
          meta={<span>Score and 90% range</span>}
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

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        aria-hidden="true"
        className="size-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  );
}

function OpeningTooltip({ point }: { point: DecisionPoint }) {
  return (
    <div className="w-72 border border-ink/20 bg-surface p-4 text-[13px] text-ink shadow-[0_4px_16px_rgba(23,21,18,0.08)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-serif text-[18px] leading-tight">{point.label}</p>
          <p className="mt-1 text-[12px] text-faint">{point.family}</p>
        </div>
        {point.breakout ? (
          <span className="text-[12px] font-medium text-accent">Breakout</span>
        ) : null}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-4 border-y border-rule py-3">
        <TooltipBand label="Opportunity" band={point.opportunity} />
        <TooltipBand label="Discovery gap" band={point.discoveryGap} />
        <TooltipBand label="Attention" band={point.demand} />
        <TooltipBand label="Release supply" band={point.supply} />
      </div>
      <dl className="numeral mt-3 grid gap-1.5 text-[12px] text-faint">
        <div className="flex justify-between gap-3">
          <dt>Evidence records</dt>
          <dd className="text-ink">{formatCompact(point.evidenceVolume)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt>Effective n (talk / listen / supply)</dt>
          <dd className="text-ink">{point.effectiveN}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt>Shrinkage (talk / listen / supply)</dt>
          <dd className="text-ink">{point.shrinkage}</dd>
        </div>
      </dl>
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
      <p className="text-[12px] text-faint">{label}</p>
      <p className="numeral mt-0.5 text-[16px] font-medium text-ink">
        {formatNumber(band.value)}
      </p>
      <p className="numeral text-[12px] text-faint">{formatInterval(band)}</p>
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
      className="focus-ring group block border-b border-rule px-5 py-4 last:border-0 hover:bg-raised/60 sm:px-6"
    >
      <div className="flex items-start gap-4">
        <span className="numeral w-6 pt-0.5 font-serif text-[20px] italic leading-none text-faint">
          {rank}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-serif text-[19px] leading-tight text-ink group-hover:underline group-hover:decoration-rule group-hover:underline-offset-4">
                {item.genre.display_name}
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                <CoverageBadge status={item.genre.coverage_status} />
                <span className="text-[12px] text-faint">
                  {item.genre.macro_family_name}
                </span>
                {item.breakout_flag ? (
                  <span className="text-[12px] font-medium text-accent">
                    Breakout
                  </span>
                ) : null}
              </div>
            </div>
            <BandValue band={item.opportunity} />
          </div>
          <p className="numeral mt-3 text-[12px] text-faint">
            Discovery gap {formatNumber(item.discovery_gap.value)}, range{" "}
            {formatInterval(item.discovery_gap)}
          </p>
        </div>
      </div>
    </Link>
  );
}
