"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  BandValue,
  CoverageExplanation,
  Panel,
  PanelHeader,
  StatusPill,
} from "@/components/ui";
import {
  formatNumber,
  formatWeek,
  modelLabel,
} from "@/lib/format";
import type {
  EstimateBand,
  ForecastItem,
  GenreTimeseries,
} from "@/lib/types";
import { palette } from "@/lib/palette";

type ChartPoint = {
  week: string;
  conversation?: number;
  conversationBand?: [number, number];
  conversationEwma?: number;
  listening?: number;
  listeningBand?: [number, number];
  listeningEwma?: number;
  supply?: number;
  supplyBand?: [number, number];
  supplyEwma?: number;
  forecastConversation?: number;
  forecastConversationBand?: [number, number];
  forecastListening?: number;
  forecastListeningBand?: [number, number];
};

function tuple(band: EstimateBand): [number, number] {
  return [band.lower, band.upper];
}

export function SceneDecisionHistory({
  timeseries,
}: {
  timeseries: GenreTimeseries;
}) {
  const points: ChartPoint[] = timeseries.history.map((history) => ({
    week: history.week,
    conversation: history.conversation?.index.value,
    conversationBand: history.conversation
      ? tuple(history.conversation.index)
      : undefined,
    conversationEwma: history.conversation?.ewma.value,
    listening: history.listening?.index.value,
    listeningBand: history.listening
      ? tuple(history.listening.index)
      : undefined,
    listeningEwma: history.listening?.ewma.value,
    supply: history.supply?.index.value,
    supplyBand: history.supply ? tuple(history.supply.index) : undefined,
    supplyEwma: history.supply?.ewma.value,
  }));
  const latest = points.at(-1);
  const publishableForecasts = timeseries.forecasts.filter(
    (forecast) => forecast.prediction_interval_80,
  );
  if (latest) {
    if (
      publishableForecasts.some(
        (forecast) => forecast.target_axis === "conversation",
      )
    ) {
      latest.forecastConversation = latest.conversation;
    }
    if (
      publishableForecasts.some(
        (forecast) => forecast.target_axis === "listening",
      )
    ) {
      latest.forecastListening = latest.listening;
    }
  }
  const forward = new Map<string, ChartPoint>();
  publishableForecasts.forEach((forecast) => {
    if (!forecast.target_week || !forecast.prediction_interval_80) return;
    const point = forward.get(forecast.target_week) ?? {
      week: forecast.target_week,
    };
    if (forecast.target_axis === "conversation") {
      point.forecastConversation = forecast.prediction_interval_80.value;
      point.forecastConversationBand = tuple(
        forecast.prediction_interval_80,
      );
    } else {
      point.forecastListening = forecast.prediction_interval_80.value;
      point.forecastListeningBand = tuple(
        forecast.prediction_interval_80,
      );
    }
    forward.set(forecast.target_week, point);
  });
  points.push(
    ...[...forward.values()].sort((left, right) =>
      left.week.localeCompare(right.week),
    ),
  );

  return (
    <Panel>
      <PanelHeader
        kicker="What changed"
        title="Conversation, listening change, and release supply"
        meta={<SeriesKeys />}
      />
      <div className="h-[470px] px-2 pb-4 pt-7 sm:px-5">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={points}
            margin={{ top: 8, right: 10, bottom: 18, left: 0 }}
          >
            <CartesianGrid
              className="chart-grid"
              strokeDasharray="2 8"
              vertical={false}
            />
            <XAxis
              dataKey="week"
              tickFormatter={formatWeek}
              tickLine={false}
              axisLine={{ stroke: palette.rule }}
              minTickGap={34}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={42}
              label={{
                value: "WITHIN-WEEK Z",
                angle: -90,
                position: "insideLeft",
                fill: palette.muted,
                fontSize: 9,
              }}
            />
            <ReferenceLine
              y={0}
              stroke={palette.faint}
              strokeDasharray="2 4"
            />
            <Tooltip
              content={({ active, payload }) => {
                const point = payload?.[0]?.payload as ChartPoint | undefined;
                return active && point ? <HistoryTooltip point={point} /> : null;
              }}
            />
            <Area
              dataKey="conversationBand"
              stroke="none"
              fill={palette.accent}
              fillOpacity={0.1}
              isAnimationActive={false}
            />
            <Area
              dataKey="listeningBand"
              stroke="none"
              fill={palette.ink}
              fillOpacity={0.06}
              isAnimationActive={false}
            />
            <Area
              dataKey="supplyBand"
              stroke="none"
              fill={palette.faint}
              fillOpacity={0.05}
              isAnimationActive={false}
            />
            <Area
              dataKey="forecastConversationBand"
              stroke="none"
              fill={palette.accent}
              fillOpacity={0.18}
              isAnimationActive={false}
            />
            <Area
              dataKey="forecastListeningBand"
              stroke="none"
              fill={palette.ink}
              fillOpacity={0.1}
              isAnimationActive={false}
            />
            <Line
              dataKey="conversation"
              stroke={palette.accent}
              strokeWidth={1.8}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              dataKey="listening"
              stroke={palette.ink}
              strokeWidth={1.35}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              dataKey="supply"
              stroke={palette.faint}
              strokeWidth={1.1}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              dataKey="conversationEwma"
              stroke={palette.accent}
              strokeOpacity={0.38}
              strokeDasharray="3 5"
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              dataKey="listeningEwma"
              stroke={palette.ink}
              strokeOpacity={0.3}
              strokeDasharray="3 5"
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              dataKey="supplyEwma"
              stroke={palette.faint}
              strokeOpacity={0.3}
              strokeDasharray="3 5"
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              dataKey="forecastConversation"
              stroke={palette.accent}
              strokeWidth={1.8}
              strokeDasharray="2 4"
              dot={{ r: 2.5, fill: palette.accent }}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              dataKey="forecastListening"
              stroke={palette.ink}
              strokeWidth={1.35}
              strokeDasharray="2 4"
              dot={{ r: 2.5, fill: palette.ink }}
              connectNulls
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

export function ForecastDecisionRecord({
  forecasts,
}: {
  forecasts: ForecastItem[];
}) {
  if (forecasts.length === 0) {
    return (
      <CoverageExplanation status="collecting_history" />
    );
  }
  return (
    <Panel>
      <PanelHeader
        kicker="What may move next"
        title="Published calls with validation next to every estimate"
        meta={
          <span className="numeral text-[9px] text-faint">
            80% prediction intervals
          </span>
        }
      />
      <div className="divide-y divide-white/[0.06]">
        {forecasts.map((forecast, index) => (
          <ForecastRow
            key={`${forecast.target_axis}-${forecast.horizon}-${index}`}
            forecast={forecast}
          />
        ))}
      </div>
    </Panel>
  );
}

function ForecastRow({ forecast }: { forecast: ForecastItem }) {
  if (
    forecast.forecast_status === "insufficient_history" ||
    !forecast.prediction_interval_80
  ) {
    return (
      <div className="grid gap-3 px-5 py-5 sm:grid-cols-[150px_1fr_auto] sm:items-center sm:px-6">
        <div>
          <p className="text-xs font-medium capitalize text-muted">
            {forecast.target_axis}
          </p>
          <p className="numeral mt-1 text-[9px] text-faint">
            horizon {forecast.horizon}
          </p>
        </div>
        <p className="text-[10px] leading-5 text-faint">
          Insufficient history: {forecast.valid_training_weeks} of 8 valid
          weeks. No prediction and no skill claim are published yet.
        </p>
        <StatusPill tone="muted">insufficient history</StatusPill>
      </div>
    );
  }
  const status = forecast.forecast_status === "ready" ? "skill" : "no_skill";
  return (
    <div className="grid gap-4 px-5 py-5 sm:grid-cols-[150px_1fr_1fr_auto] sm:items-center sm:px-6">
      <div>
        <p className="text-xs font-medium capitalize text-ink">
          {forecast.target_axis}
        </p>
        <p className="numeral mt-1 text-[9px] text-faint">
          {forecast.target_week ?? "next week"} · h{forecast.horizon}
        </p>
      </div>
      <BandValue band={forecast.prediction_interval_80} />
      <div className="numeral text-[9px] leading-5 text-faint">
        <p>
          {forecast.model ? modelLabel(forecast.model) : "Naive"} · genre MASE{" "}
          {formatScore(forecast.genre_validation?.mase)}
        </p>
        <p>
          family MASE {formatScore(forecast.family_validation?.mase)} ·
          coverage {formatCoverage(forecast.family_validation?.coverage_80)}
        </p>
      </div>
      <StatusPill tone={status === "skill" ? "accent" : "muted"}>
        {status}
      </StatusPill>
    </div>
  );
}

function HistoryTooltip({ point }: { point: ChartPoint }) {
  return (
    <div className="w-64 border border-rule bg-surface shadow-[0_4px_16px_rgba(23,21,18,0.08)] p-4">
      <p className="numeral text-[10px] text-muted">
        {formatWeek(point.week)}
      </p>
      <div className="mt-3 space-y-2">
        <TooltipBand
          label="Conversation"
          value={point.conversation}
          band={point.conversationBand}
        />
        <TooltipBand
          label="Listening change"
          value={point.listening}
          band={point.listeningBand}
        />
        <TooltipBand
          label="Release supply"
          value={point.supply}
          band={point.supplyBand}
        />
        <TooltipBand
          label="Forecast · conversation"
          value={point.forecastConversation}
          band={point.forecastConversationBand}
        />
        <TooltipBand
          label="Forecast · listening"
          value={point.forecastListening}
          band={point.forecastListeningBand}
        />
      </div>
    </div>
  );
}

function TooltipBand({
  label,
  value,
  band,
}: {
  label: string;
  value?: number;
  band?: [number, number];
}) {
  if (value === undefined || !band) return null;
  return (
    <div className="flex items-start justify-between gap-4 text-[9px]">
      <span className="text-faint">{label}</span>
      <span className="numeral text-right text-muted">
        {formatNumber(value)}
        <br />
        <span className="text-faint">
          {formatNumber(band[0])} — {formatNumber(band[1])}
        </span>
      </span>
    </div>
  );
}

function SeriesKeys() {
  return (
    <div className="hidden items-center gap-4 text-[9px] text-faint sm:flex">
      <span className="text-accent">Conversation</span>
      <span className="text-ink">Listening change</span>
      <span className="text-faint">Release supply</span>
    </div>
  );
}

function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "—"
    : value.toFixed(2);
}

function formatCoverage(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "—"
    : `${Math.round(value * 100)}%`;
}
