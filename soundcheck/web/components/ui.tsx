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
    <div className="mb-8 grid gap-8 border-b border-ink pb-8 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
      <div className="max-w-4xl">
        <p className="mb-4 text-[13px] font-medium text-accent">{eyebrow}</p>
        <h1 className="text-[38px] font-normal leading-[1.05] tracking-[-0.015em] text-ink sm:text-[52px]">
          {title}
        </h1>
        <p className="mt-5 max-w-2xl font-serif text-[20px] leading-[1.45] text-muted">
          {description}
        </p>
      </div>
      {action ? <div className="md:pb-1.5">{action}</div> : null}
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
    <section className={`border border-rule bg-surface ${className}`}>
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
    <div className="flex items-start justify-between gap-6 border-b border-rule px-5 py-4 sm:px-6">
      <div>
        <p className="text-[12px] text-faint">{kicker}</p>
        <h2 className="mt-1 text-[22px] leading-tight text-ink">{title}</h2>
      </div>
      {meta ? <div className="pt-0.5 text-right text-[12px] text-faint">{meta}</div> : null}
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
        className={`numeral text-ink ${
          large
            ? "font-serif text-[30px] leading-none tracking-[-0.01em]"
            : "text-[16px] font-medium"
        }`}
      >
        {formatNumber(band.value, digits)}
      </span>
      <span className="numeral mt-1 text-[12px] text-faint">
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
    <div role="alert" className="border-t-2 border-accent py-8">
      <h2 className="text-[26px] leading-tight text-ink">{title}</h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-6 text-muted">
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
      className="mt-4 border-l-2 border-caution py-0.5 pl-4 text-[13px] leading-5 text-muted"
    >
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
    <p className="numeral mb-8 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-[13px] text-muted">
      <span>
        Lens: <strong className="font-medium text-ink">{family}</strong>
      </span>
      <Separator />
      <span>
        Compared with{" "}
        <strong className="font-medium text-ink">
          {context === "peer_family" ? "family peers" : "all genres"}
        </strong>
      </span>
      <Separator />
      <span>{taxonomyVersion}</span>
      {readyGenres !== undefined ? (
        <>
          <Separator />
          <span>
            <strong className="font-medium text-ink">{readyGenres}</strong>{" "}
            decision-ready
            {partialGenres ? `, ${partialGenres} still collecting` : ""}
          </span>
        </>
      ) : null}
    </p>
  );
}

function Separator() {
  return (
    <span aria-hidden="true" className="text-faint">
      ·
    </span>
  );
}

export function CoverageBadge({
  status,
}: {
  status: CoverageStatus;
}) {
  const tone =
    status === "ready"
      ? "text-confirm"
      : status === "unsupported"
        ? "text-faint"
        : "text-caution";
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap text-[12px] font-medium ${tone}`}
    >
      <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
      {sentenceCase(coverageLabel(status))}
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
      className={`border-l-2 border-caution pl-4 ${compact ? "py-0.5" : "py-1"}`}
    >
      <p className="text-[14px] font-medium text-caution">
        {coverageTitle(status)}
      </p>
      <p className="mt-1 max-w-2xl text-[13px] leading-5 text-muted">
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
    <div className="border-y border-rule py-10">
      <p className="text-[13px] font-medium text-caution">{eyebrow}</p>
      <h2 className="mt-2 max-w-2xl text-[28px] leading-tight text-ink">
        {title}
      </h2>
      <p className="mt-3 max-w-2xl text-[15px] leading-6 text-muted">
        {message}
      </p>
      {href && linkLabel ? (
        <Link
          href={href}
          className="focus-ring mt-5 inline-block text-[14px] font-medium text-accent underline decoration-accent/40 underline-offset-4 hover:decoration-accent"
        >
          {linkLabel} →
        </Link>
      ) : null}
    </div>
  );
}

export function LoadingState() {
  return (
    <div
      role="status"
      aria-label="Loading"
      className="border-y border-rule py-16 text-center font-serif text-[17px] italic text-faint"
    >
      Loading…
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
    neutral: "border-ink/25 text-muted",
    accent: "border-accent/40 text-accent",
    muted: "border-rule text-faint",
  }[tone];
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap border px-1.5 py-0.5 text-[11px] font-medium ${toneClass}`}
    >
      {children}
    </span>
  );
}

function sentenceCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
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
