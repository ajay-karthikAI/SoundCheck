"use client";

import Link from "next/link";
import {
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import {
  CoverageBadge,
  Panel,
  PanelHeader,
} from "@/components/ui";
import {
  formatInterval,
  formatNumber,
  openingColor,
} from "@/lib/format";
import type { SceneMapPoint } from "@/lib/types";

type FamilyCentroid = {
  x: number;
  y: number;
  label: string;
};

export function AdjacentScenesMap({
  points,
}: {
  points: SceneMapPoint[];
}) {
  const centroids = familyCentroids(points);
  const familyCounts = new Map<string, number>();
  points.forEach((point) => {
    familyCounts.set(
      point.genre.macro_family_name,
      (familyCounts.get(point.genre.macro_family_name) ?? 0) + 1,
    );
  });
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_330px]">
      <Panel>
        <PanelHeader
          kicker="Taxonomy-v2 scene geometry"
          title="Creative neighborhoods, grouped by macro family"
          meta={
            <span className="numeral text-[9px] text-white/28">
              color = opportunity · size = evidence
            </span>
          }
        />
        <div className="h-[590px] p-3">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 32, right: 32, bottom: 24, left: 12 }}>
              <CartesianGrid
                className="chart-grid"
                strokeDasharray="2 10"
              />
              <XAxis
                type="number"
                dataKey="x"
                tick={false}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                type="number"
                dataKey="y"
                tick={false}
                tickLine={false}
                axisLine={false}
              />
              <ZAxis
                type="number"
                dataKey="evidence_volume"
                range={[28, 150]}
              />
              <Tooltip
                cursor={{ stroke: "rgba(255,255,255,.08)" }}
                content={({ active, payload }) => {
                  const point = payload?.[0]?.payload as
                    | SceneMapPoint
                    | undefined;
                  return active && point ? (
                    <SceneTooltip point={point} />
                  ) : null;
                }}
              />
              <Scatter data={points} isAnimationActive={false}>
                {points.map((point) => (
                  <Cell
                    key={point.genre.genre_id}
                    fill={openingColor(point.opportunity?.value ?? null)}
                    fillOpacity={
                      point.genre.coverage_status === "ready" ? 0.78 : 0.18
                    }
                    stroke="rgba(255,255,255,.38)"
                    strokeWidth={0.55}
                    className="chart-dot"
                  />
                ))}
              </Scatter>
              <Scatter
                data={centroids}
                fill="transparent"
                isAnimationActive={false}
              >
                <LabelList
                  dataKey="label"
                  position="top"
                  fill="rgba(255,255,255,.33)"
                  fontSize={9}
                  fontFamily="var(--font-geist-mono)"
                />
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <Panel className="overflow-hidden">
        <PanelHeader
          kicker="Macro-family index"
          title="Navigate a scene cluster"
          meta={
            <span className="numeral text-[9px] text-white/28">
              {familyCounts.size} families
            </span>
          }
        />
        <div className="max-h-[590px] overflow-y-auto">
          {[...familyCounts.entries()]
            .sort(([left], [right]) => left.localeCompare(right))
            .map(([family, count]) => (
              <div
                key={family}
                className="border-b hairline px-5 py-4 last:border-0"
              >
                <div className="flex items-center justify-between">
                  <p className="text-xs text-white/60">{family}</p>
                  <span className="numeral text-[9px] text-white/25">
                    {count} genres
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {points
                    .filter(
                      (point) =>
                        point.genre.macro_family_name === family,
                    )
                    .slice(0, 4)
                    .map((point) => (
                      <Link
                        key={point.genre.genre_id}
                        href={`/genre/${point.genre.slug}`}
                        className="focus-ring rounded border hairline px-2 py-1 text-[9px] text-white/35 hover:text-white"
                      >
                        {point.genre.display_name}
                      </Link>
                    ))}
                </div>
              </div>
            ))}
        </div>
      </Panel>
    </div>
  );
}

function SceneTooltip({ point }: { point: SceneMapPoint }) {
  return (
    <div className="w-64 rounded-md border border-white/10 bg-[#111114] p-4 text-xs">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium">{point.genre.display_name}</p>
          <p className="mt-1 text-[9px] text-white/30">
            {point.genre.macro_family_name}
          </p>
        </div>
        <CoverageBadge status={point.genre.coverage_status} />
      </div>
      {point.opportunity ? (
        <div className="mt-4 border-t hairline pt-3">
          <p className="text-[9px] uppercase tracking-[0.1em] text-white/27">
            Opportunity · 90% interval
          </p>
          <p className="numeral mt-2 text-sm text-white/75">
            {formatNumber(point.opportunity.value)}
          </p>
          <p className="numeral mt-1 text-[9px] text-white/28">
            {formatInterval(point.opportunity)}
          </p>
        </div>
      ) : (
        <p className="mt-4 border-t hairline pt-3 text-[10px] leading-4 text-white/30">
          No estimate is shown because this genre has not cleared its evidence
          gate.
        </p>
      )}
    </div>
  );
}

function familyCentroids(points: SceneMapPoint[]): FamilyCentroid[] {
  const grouped = new Map<
    string,
    { x: number; y: number; count: number; label: string }
  >();
  points.forEach((point) => {
    const current = grouped.get(point.genre.macro_family_id) ?? {
      x: 0,
      y: 0,
      count: 0,
      label: point.genre.macro_family_name.toUpperCase(),
    };
    current.x += point.x;
    current.y += point.y;
    current.count += 1;
    grouped.set(point.genre.macro_family_id, current);
  });
  return [...grouped.values()].map((group) => ({
    x: group.x / group.count,
    y: group.y / group.count,
    label: group.label,
  }));
}
