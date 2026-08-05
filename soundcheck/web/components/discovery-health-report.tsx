"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { BandValue, Panel, PanelHeader } from "@/components/ui";
import {
  formatInterval,
  formatNumber,
  formatWeek,
} from "@/lib/format";
import type {
  EcosystemPoint,
  EstimateBand,
} from "@/lib/types";

type HealthChartRow = {
  week: string;
  entropy: number | null;
  entropyRange: [number, number] | null;
  effective: number | null;
  effectiveRange: [number, number] | null;
  hhi: number | null;
  hhiRange: [number, number] | null;
  churn: number | null;
  churnRange: [number, number] | null;
};

export function DiscoveryHealthReport({
  weeklyHealth,
}: {
  weeklyHealth: EcosystemPoint[];
}) {
  const latest = weeklyHealth.at(-1);
  if (!latest) return null;
  const rows: HealthChartRow[] = weeklyHealth.map((week) => ({
    week: week.week,
    entropy: week.listening_entropy?.value ?? null,
    entropyRange: toRange(week.listening_entropy),
    effective: week.effective_genres?.value ?? null,
    effectiveRange: toRange(week.effective_genres),
    hhi: week.conversation_hhi?.value ?? null,
    hhiRange: toRange(week.conversation_hhi),
    churn: week.scene_churn_jaccard_4w?.value ?? null,
    churnRange: toRange(week.scene_churn_jaccard_4w),
  }));
  return (
    <div className="space-y-6">
      <div className="grid gap-px overflow-hidden rounded-lg border hairline bg-white/[0.08] sm:grid-cols-2 lg:grid-cols-4">
        <HealthCard
          label="Listening diversity"
          band={latest.listening_entropy}
          detail="Shannon entropy"
        />
        <HealthCard
          label="Effective genres"
          band={latest.effective_genres}
          detail="exp(entropy)"
        />
        <HealthCard
          label="Conversation concentration"
          band={latest.conversation_hhi}
          detail="Lower HHI is broader"
        />
        <HealthCard
          label="Four-week scene continuity"
          band={latest.scene_churn_jaccard_4w}
          detail="Lower means faster churn"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <HealthChart
          title="Are listening paths widening?"
          kicker="Diversity"
          data={rows}
          valueKey="effective"
          rangeKey="effectiveRange"
        />
        <HealthChart
          title="Is conversation concentrating?"
          kicker="Concentration"
          data={rows}
          valueKey="hhi"
          rangeKey="hhiRange"
        />
      </div>

      <Panel>
        <PanelHeader
          kicker="Decision read"
          title="What the latest week says about discovery"
          meta={
            <span className="numeral text-[9px] text-white/28">
              {formatWeek(latest.week)}
            </span>
          }
        />
        <div className="grid gap-px bg-white/[0.06] md:grid-cols-3">
          <HealthRead
            title="Breadth"
            text={breadthRead(latest)}
          />
          <HealthRead
            title="Concentration"
            text={concentrationRead(latest)}
          />
          <HealthRead
            title="Scene renewal"
            text={churnRead(latest)}
          />
        </div>
      </Panel>
    </div>
  );
}

function HealthCard({
  label,
  band,
  detail,
}: {
  label: string;
  band: EstimateBand | null;
  detail: string;
}) {
  return (
    <div className="bg-surface px-5 py-5">
      <p className="text-[9px] uppercase tracking-[0.12em] text-white/28">
        {label}
      </p>
      <div className="mt-3 min-h-10">
        {band ? (
          <BandValue band={band} large />
        ) : (
          <span className="numeral text-sm text-white/25">Unavailable</span>
        )}
      </div>
      <p className="mt-3 text-[9px] text-white/24">{detail}</p>
    </div>
  );
}

function HealthChart({
  title,
  kicker,
  data,
  valueKey,
  rangeKey,
}: {
  title: string;
  kicker: string;
  data: HealthChartRow[];
  valueKey: "effective" | "hhi";
  rangeKey: "effectiveRange" | "hhiRange";
}) {
  return (
    <Panel>
      <PanelHeader kicker={kicker} title={title} />
      <div className="h-72 px-3 py-5">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data}>
            <CartesianGrid
              className="chart-grid"
              strokeDasharray="2 8"
              vertical={false}
            />
            <XAxis
              dataKey="week"
              tickFormatter={formatWeek}
              tickLine={false}
              axisLine={false}
              minTickGap={36}
            />
            <YAxis tickLine={false} axisLine={false} width={42} />
            <Tooltip content={<HealthTooltip valueKey={valueKey} />} />
            <Area
              dataKey={rangeKey}
              stroke="none"
              fill="#6872f3"
              fillOpacity={0.1}
              isAnimationActive={false}
            />
            <Line
              dataKey={valueKey}
              stroke="#8189ff"
              strokeWidth={1.5}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

function HealthTooltip({
  active,
  payload,
  label,
  valueKey,
}: {
  active?: boolean;
  payload?: Array<{ payload: HealthChartRow }>;
  label?: string;
  valueKey: "effective" | "hhi";
}) {
  const row = payload?.[0]?.payload;
  const value = row?.[valueKey];
  const range =
    valueKey === "effective" ? row?.effectiveRange : row?.hhiRange;
  if (!active || !row || value == null || !range) return null;
  return (
    <div className="rounded-md border border-white/10 bg-[#111114] p-3 text-xs">
      <p className="numeral text-[9px] text-white/30">
        {formatWeek(label ?? row.week)}
      </p>
      <p className="numeral mt-2 text-white/75">
        {formatNumber(value)}
      </p>
      <p className="numeral mt-1 text-[9px] text-white/30">
        {formatNumber(range[0])} — {formatNumber(range[1])}
      </p>
    </div>
  );
}

function HealthRead({
  title,
  text,
}: {
  title: string;
  text: string;
}) {
  return (
    <div className="bg-surface px-5 py-5">
      <p className="numeral text-[9px] uppercase tracking-[0.12em] text-white/27">
        {title}
      </p>
      <p className="mt-2 text-xs leading-5 text-white/48">{text}</p>
    </div>
  );
}

function toRange(
  band: EstimateBand | null,
): [number, number] | null {
  return band ? [band.lower, band.upper] : null;
}

function breadthRead(point: EcosystemPoint): string {
  return point.effective_genres
    ? `${formatNumber(point.effective_genres.value)} effective genres, with a 90% range of ${formatInterval(point.effective_genres)}.`
    : "Listening breadth is unavailable because valid cross-genre listening change is incomplete.";
}

function concentrationRead(point: EcosystemPoint): string {
  return point.conversation_hhi
    ? `Conversation HHI is ${formatNumber(point.conversation_hhi.value)}, with a 90% range of ${formatInterval(point.conversation_hhi)}.`
    : "Conversation concentration is unavailable for this comparison set.";
}

function churnRead(point: EcosystemPoint): string {
  return point.scene_churn_jaccard_4w
    ? `Top scenes retain ${formatNumber(point.scene_churn_jaccard_4w.value)} Jaccard similarity to four weeks ago, range ${formatInterval(point.scene_churn_jaccard_4w)}.`
    : "Four-week scene churn needs more comparable history.";
}
