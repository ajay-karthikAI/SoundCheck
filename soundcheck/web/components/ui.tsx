import {
  AlertCircle,
  ArrowRight,
  Database,
  LoaderCircle,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { formatInterval, formatNumber } from "@/lib/format";
import type { EstimateBand } from "@/lib/types";
import type {
  ComparisonContext,
  CoverageStatus,
} from "@/lib/types";

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-10 grid gap-6 border-b hairline pb-10 md:grid-cols-[1fr_auto] md:items-end">
      <div className="max-w-3xl">
        <p className="numeral mb-3 text-[10px] uppercase tracking-[0.18em] text-accent">
          {eyebrow}
        </p>
        <h1 className="max-w-2xl text-3xl font-medium tracking-[-0.035em] text-white sm:text-[40px] sm:leading-[1.08]">
          {title}
        </h1>
        <p className="mt-4 max-w-2xl text-sm leading-6 text-white/48">
          {description}
        </p>
      </div>
      {action}
    </div>
  );
}

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-lg border hairline bg-surface ${className}`}
    >
      {children}
    </section>
  );
}

export function PanelHeader({
  kicker,
  title,
  meta,
}: {
  kicker: string;
  title: string;
  meta?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-6 border-b hairline px-5 py-4 sm:px-6">
      <div>
        <p className="numeral text-[9px] uppercase tracking-[0.16em] text-white/30">
          {kicker}
        </p>
        <h2 className="mt-1 text-sm font-medium text-white/85">{title}</h2>
      </div>
      {meta}
    </div>
  );
}

export function BandValue({
  band,
  digits = 2,
  large = false,
}: {
  band: EstimateBand;
  digits?: number;
  large?: boolean;
}) {
  return (
    <span className="inline-flex flex-col items-end">
      <span
        className={`numeral text-white ${
          large ? "text-2xl tracking-[-0.04em]" : "text-sm"
        }`}
      >
        {formatNumber(band.value, digits)}
      </span>
      <span className="numeral mt-1 text-[10px] text-white/32">
        {formatInterval(band, digits)}
      </span>
    </span>
  );
}

export function ErrorState({
  title = "This decision could not be prepared",
  message,
}: {
  title?: string;
  message: string;
}) {
  return (
    <div
      role="alert"
      className="flex min-h-64 flex-col items-center justify-center rounded-lg border hairline bg-surface px-6 text-center"
    >
      <AlertCircle className="mb-4 text-white/28" size={20} />
      <h2 className="text-sm font-medium">{title}</h2>
      <p className="mt-2 max-w-md text-xs leading-5 text-white/40">
        {message}
      </p>
    </div>
  );
}

export function InlineNotice({
  message,
}: {
  message: string;
}) {
  return (
    <div
      role="status"
      className="mt-4 flex items-start gap-2 rounded-md border hairline bg-white/[0.018] px-4 py-3 text-[10px] leading-4 text-white/34"
    >
      <AlertCircle
        aria-hidden="true"
        className="mt-0.5 shrink-0 text-white/25"
        size={12}
      />
      {message}
    </div>
  );
}

export function ScopeContext({
  family,
  context,
  taxonomyVersion,
  readyGenres,
  partialGenres,
}: {
  family: string;
  context: ComparisonContext;
  taxonomyVersion: string;
  readyGenres?: number;
  partialGenres?: number;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-md border hairline bg-white/[0.018] px-4 py-3 text-[10px] text-white/34">
      <span>
        Lens <strong className="font-medium text-white/65">{family}</strong>
      </span>
      <span>
        Comparison{" "}
        <strong className="font-medium text-white/65">
          {context === "peer_family" ? "family peers" : "all genres"}
        </strong>
      </span>
      <span className="numeral">{taxonomyVersion}</span>
      {readyGenres !== undefined ? (
        <span className="numeral text-white/45">
          {readyGenres} decision-ready
          {partialGenres ? ` · ${partialGenres} still collecting` : ""}
        </span>
      ) : null}
    </div>
  );
}

export function CoverageBadge({
  status,
}: {
  status: CoverageStatus;
}) {
  const ready = status === "ready";
  return (
    <span
      className={`numeral inline-flex rounded-full border px-2 py-1 text-[8px] uppercase tracking-[0.1em] ${
        ready
          ? "border-accent/25 bg-accent/[0.08] text-[#aeb4ff]"
          : status === "unsupported"
            ? "border-white/[0.05] text-white/22"
            : "border-[#b99c6f]/20 bg-[#b99c6f]/[0.06] text-[#c8b086]"
      }`}
    >
      {coverageLabel(status)}
    </span>
  );
}

export function CoverageExplanation({
  status,
  compact = false,
}: {
  status: CoverageStatus;
  compact?: boolean;
}) {
  if (status === "ready") return null;
  return (
    <div
      role="status"
      className={`rounded-md border border-[#b99c6f]/15 bg-[#b99c6f]/[0.035] ${
        compact ? "px-3 py-2" : "px-5 py-4"
      }`}
    >
      <p className="text-xs font-medium text-[#cfb98d]">
        {coverageTitle(status)}
      </p>
      <p className="mt-1 max-w-2xl text-[10px] leading-5 text-white/35">
        {coverageDescription(status)}
      </p>
    </div>
  );
}

export function EmptyState({
  eyebrow = "Decision not ready",
  title,
  message,
  href,
  linkLabel,
}: {
  eyebrow?: string;
  title: string;
  message: string;
  href?: string;
  linkLabel?: string;
}) {
  return (
    <div className="flex min-h-72 flex-col items-center justify-center rounded-lg border hairline bg-surface px-6 text-center">
      <Database className="mb-5 text-white/22" size={21} strokeWidth={1.5} />
      <p className="numeral text-[9px] uppercase tracking-[0.16em] text-white/28">
        {eyebrow}
      </p>
      <h2 className="mt-3 text-base font-medium">{title}</h2>
      <p className="mt-2 max-w-md text-xs leading-5 text-white/40">
        {message}
      </p>
      {href && linkLabel ? (
        <Link
          href={href}
          className="focus-ring mt-5 inline-flex items-center gap-2 rounded-sm text-xs text-accent hover:text-white"
        >
          {linkLabel}
          <ArrowRight size={13} />
        </Link>
      ) : null}
    </div>
  );
}

export function LoadingState() {
  return (
    <div className="flex min-h-72 items-center justify-center rounded-lg border hairline bg-surface">
      <LoaderCircle
        aria-label="Loading"
        className="animate-spin text-white/25"
        size={20}
      />
    </div>
  );
}

export function StatusPill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "muted";
}) {
  const toneClass = {
    neutral: "border-white/10 bg-white/[0.035] text-white/55",
    accent: "border-accent/30 bg-accent/10 text-[#aeb4ff]",
    muted: "border-white/[0.06] bg-transparent text-white/28",
  }[tone];
  return (
    <span
      className={`numeral inline-flex items-center rounded-full border px-2 py-1 text-[9px] uppercase tracking-[0.1em] ${toneClass}`}
    >
      {children}
    </span>
  );
}

export function coverageLabel(status: CoverageStatus): string {
  const labels: Record<CoverageStatus, string> = {
    ready: "ready",
    collecting_history: "collecting history",
    insufficient_listening: "listening incomplete",
    insufficient_conversation: "conversation incomplete",
    insufficient_supply: "release supply incomplete",
    insufficient_resolution: "identity matching incomplete",
    unsupported: "unsupported",
    not_observed: "not observed",
  };
  return labels[status];
}

function coverageTitle(status: CoverageStatus): string {
  if (status === "collecting_history") {
    return "Insufficient history—not a zero signal";
  }
  if (status === "unsupported") {
    return "This genre is not eligible for a claim";
  }
  if (status === "not_observed") {
    return "No cross-source observation yet";
  }
  return "Insufficient evidence for a decision";
}

function coverageDescription(status: CoverageStatus): string {
  const descriptions: Record<CoverageStatus, string> = {
    ready:
      "Conversation, listening change, and release supply clear the published evidence gates.",
    collecting_history:
      "Soundcheck needs consecutive weekly Last.fm snapshots before it can measure listening change or validate a forecast.",
    insufficient_listening:
      "Listening evidence is missing or too thin. Lifetime totals are never substituted for weekly movement.",
    insufficient_conversation:
      "There are too few resolved public music posts to support a conversation estimate.",
    insufficient_supply:
      "MusicBrainz release evidence is too incomplete to compare audience demand with release supply.",
    insufficient_resolution:
      "Too few artists can be linked confidently across sources, so Soundcheck withholds the estimate.",
    unsupported:
      "The available public sources cannot support this genre under the current taxonomy and evidence rules.",
    not_observed:
      "The collectors have not observed enough source material to evaluate this genre yet.",
  };
  return descriptions[status];
}
