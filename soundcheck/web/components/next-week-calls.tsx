import { ArrowRight, ShieldCheck } from "lucide-react";
import Link from "next/link";

import {
  BandValue,
  CoverageBadge,
  Panel,
  StatusPill,
} from "@/components/ui";
import {
  formatPlain,
  formatWeek,
  modelLabel,
} from "@/lib/format";
import type {
  ForecastItem,
  NextUpItem,
} from "@/lib/types";

export function NextWeekCalls({
  calls,
}: {
  calls: NextUpItem[];
}) {
  return (
    <div className="space-y-3">
      {calls.map((call) => (
        <article
          key={call.genre.genre_id}
          className={`border hairline bg-surface ${
            call.skill_status === "no_skill" ? "opacity-60" : ""
          }`}
        >
          <Link
            href={`/genre/${call.genre.slug}`}
            className="focus-ring group grid gap-6 px-5 py-6 sm:px-7 lg:grid-cols-[58px_minmax(190px,1fr)_minmax(220px,.8fr)_minmax(260px,1fr)_24px] lg:items-center"
          >
            <div>
              <p className="numeral text-[9px] text-faint">
                Rank
              </p>
              <p className="numeral mt-1 text-3xl tracking-[-0.05em] text-ink">
                {String(call.rank).padStart(2, "0")}
              </p>
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-medium tracking-[-0.025em]">
                  {call.genre.display_name}
                </h2>
                <StatusPill
                  tone={call.skill_status === "skill" ? "accent" : "muted"}
                >
                  {call.skill_status}
                </StatusPill>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <CoverageBadge status={call.genre.coverage_status} />
                <span className="text-[9px] text-faint">
                  {call.genre.macro_family_name}
                </span>
              </div>
              <p className="mt-3 text-xs leading-5 text-faint">
                {call.skill_status === "skill"
                  ? "The selected models beat persistence inside this genre family."
                  : "No model beat persistence, so the naive call remains visible."}
              </p>
            </div>
            <div className="border-l hairline pl-5">
              <p className="numeral text-[9px] text-faint">
                Predicted gain · 80% interval
              </p>
              <div className="mt-2">
                <BandValue band={call.predicted_gain} large />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <ModelRecord
                label="Conversation"
                model={call.conversation.model}
                mase={call.conversation.mase}
                coverage={call.conversation.coverage_80}
                status={call.conversation.forecast_status}
              />
              <ModelRecord
                label="Listening"
                model={call.listening.model}
                mase={call.listening.mase}
                coverage={call.listening.coverage_80}
                status={call.listening.forecast_status}
              />
            </div>
            <ArrowRight
              size={15}
              className="text-faint group-hover:text-accent"
            />
          </Link>
        </article>
      ))}
    </div>
  );
}

function ModelRecord({
  label,
  model,
  mase,
  coverage,
  status,
}: {
  label: string;
  model: string;
  mase: number | null;
  coverage: number;
  status: string;
}) {
  return (
    <div className="border hairline bg-ink/[0.018] p-3">
      <p className="text-[9px] text-faint">
        {label}
      </p>
      <p className="mt-2 text-xs text-muted">{modelLabel(model)}</p>
      <p className="numeral mt-2 text-[9px] text-faint">
        MASE {mase === null ? "—" : formatPlain(mase)} · coverage{" "}
        {formatPlain(coverage, 2)}
      </p>
      <p className="numeral mt-1 text-[8px] text-faint">{status}</p>
    </div>
  );
}

export function ForecastReadiness({
  forecasts,
}: {
  forecasts: ForecastItem[];
}) {
  const coldGenres = new Map(
    forecasts
      .filter(
        (forecast) =>
          forecast.forecast_status === "insufficient_history" ||
          forecast.forecast_status === "insufficient_evidence",
      )
      .map((forecast) => [forecast.genre.genre_id, forecast]),
  );
  if (coldGenres.size === 0) return null;
  return (
    <Panel className="mt-6 overflow-hidden">
      <div className="border-b hairline px-5 py-4">
        <p className="numeral text-[9px] text-faint">
          Forecast readiness
        </p>
        <h2 className="mt-1 text-sm font-medium">
          Known genres still building a valid history
        </h2>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3">
        {[...coldGenres.values()].slice(0, 9).map((forecast) => (
          <Link
            key={forecast.genre.genre_id}
            href={`/genre/${forecast.genre.slug}`}
            className="focus-ring border-b border-r hairline px-5 py-4 hover:bg-ink/[0.025]"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-muted">
                {forecast.genre.display_name}
              </p>
              <span className="numeral text-[9px] text-faint">
                {forecast.valid_training_weeks}/8 weeks
              </span>
            </div>
            <p className="mt-2 text-[10px] leading-4 text-faint">
              Insufficient history means no prediction and no skill claim is
              made yet.
            </p>
          </Link>
        ))}
      </div>
    </Panel>
  );
}

export function ForecastIssueSummary({
  call,
  count,
}: {
  call: NextUpItem;
  count: number;
}) {
  return (
    <div className="min-w-48 border hairline bg-surface px-4 py-3">
      <p className="numeral text-[9px] text-faint">
        Issue · {formatWeek(call.target_week)}
      </p>
      <div className="mt-2 flex items-center justify-between gap-4">
        <span className="text-xs text-muted">{count} calls</span>
        <ShieldCheck size={13} className="text-accent" />
      </div>
    </div>
  );
}

export function PredictionIntervalExplainer() {
  return (
    <div className="border hairline bg-ink/[0.018] px-5 py-4 text-xs leading-5 text-faint">
      <p className="font-medium text-muted">
        How to read the 80% prediction interval
      </p>
      <p className="mt-1 max-w-3xl">
        Across similarly constructed held-out forecasts, about eight in ten
        outcomes should land inside this range. A wide or zero-crossing range
        is useful uncertainty—not permission to treat the midpoint as certain.
      </p>
    </div>
  );
}
