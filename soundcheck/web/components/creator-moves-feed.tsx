import { ArrowUpRight, Check } from "lucide-react";
import Link from "next/link";

import {
  BandValue,
  CoverageBadge,
  Panel,
  StatusPill,
} from "@/components/ui";
import {
  blueskyUrl,
  formatPlain,
  modelLabel,
  musicbrainzUrl,
} from "@/lib/format";
import type { CreatorBrief } from "@/lib/types";

export function CreatorMovesFeed({
  briefs,
}: {
  briefs: CreatorBrief[];
}) {
  return (
    <div className="grid gap-5">
      {briefs.map((brief) => (
        <Panel key={brief.brief_id} className="overflow-hidden">
          <article className="grid gap-8 p-6 md:grid-cols-[minmax(0,1fr)_220px] md:p-8">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill tone="accent">
                  {brief.genre.display_name}
                </StatusPill>
                <CoverageBadge status={brief.genre.coverage_status} />
                <span className="numeral text-[9px] text-white/24">
                  {brief.genre.macro_family_name} · {brief.week}
                </span>
              </div>
              <h2 className="mt-5 max-w-2xl text-2xl font-medium tracking-[-0.035em] text-white/90">
                {brief.headline}
              </h2>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-white/45">
                {brief.rationale}
              </p>
              <ul className="mt-6 grid gap-3">
                {brief.recommended_actions.map((action) => (
                  <li
                    key={action}
                    className="flex gap-3 text-xs leading-5 text-white/62"
                  >
                    <Check
                      size={13}
                      className="mt-1 shrink-0 text-accent"
                    />
                    {action}
                  </li>
                ))}
              </ul>
            </div>
            <aside className="border-t hairline pt-6 md:border-l md:border-t-0 md:pl-8 md:pt-0">
              <p className="text-[9px] uppercase tracking-[0.14em] text-white/28">
                Opening score · 90% range
              </p>
              <div className="mt-4 flex justify-start">
                <BandValue band={brief.opportunity} large />
              </div>
              <div className="mt-5 border-t hairline pt-5">
                <p className="text-[9px] uppercase tracking-[0.12em] text-white/25">
                  Forward direction · 80% interval
                </p>
                <div className="mt-3">
                  <BandValue band={brief.forecast_direction} />
                </div>
                <p className="numeral mt-3 text-[9px] text-white/30">
                  {modelLabel(brief.forecast_model)} · MASE{" "}
                  {brief.backtest_mase === null
                    ? "—"
                    : formatPlain(brief.backtest_mase)}{" "}
                  ·{" "}
                  {brief.backtest_mase !== null &&
                  brief.backtest_mase < 1
                    ? "skill"
                    : "no_skill"}
                </p>
              </div>
              <Link
                href={`/genre/${brief.genre.slug}`}
                className="focus-ring mt-7 inline-flex items-center gap-2 rounded-sm text-xs text-accent hover:text-white"
              >
                Inspect the decision evidence
                <ArrowUpRight size={12} />
              </Link>
              {brief.evidence_uris.length > 0 ? (
                <div className="mt-7 border-t hairline pt-5">
                  <p className="text-[9px] uppercase tracking-[0.12em] text-white/25">
                    Evidence records
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {brief.evidence_uris.map((uri, index) => (
                      <a
                        key={uri}
                        href={sourceRecordUrl(uri)}
                        target="_blank"
                        rel="noreferrer"
                        className="focus-ring numeral rounded-sm border hairline px-2 py-1 text-[9px] text-white/35 hover:border-white/20 hover:text-white/70"
                      >
                        record {index + 1}
                      </a>
                    ))}
                  </div>
                </div>
              ) : null}
            </aside>
          </article>
        </Panel>
      ))}
    </div>
  );
}

function sourceRecordUrl(uri: string): string {
  if (uri.startsWith("https://") || uri.startsWith("http://")) return uri;
  if (uri.startsWith("at://")) {
    const [, , did = "", , recordKey = ""] = uri.split("/");
    return blueskyUrl(uri, did || recordKey);
  }
  return musicbrainzUrl(uri);
}
