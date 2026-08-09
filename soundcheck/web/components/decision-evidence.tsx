import { ExternalLink } from "lucide-react";

import { InlineNotice, Panel, PanelHeader } from "@/components/ui";
import {
  blueskyUrl,
  formatNumber,
  lastfmUrl,
  musicbrainzUrl,
} from "@/lib/format";
import type { GenreEvidenceBundle } from "@/lib/types";

export function DecisionEvidence({
  evidence,
}: {
  evidence: GenreEvidenceBundle;
}) {
  const sourceRecordCount =
    evidence.conversation.length +
    evidence.listening.length +
    evidence.supply.length;
  return (
    <Panel>
      <PanelHeader
        kicker="Why this recommendation exists"
        title="Inspect the public source records before acting"
        meta={
          <span className="numeral text-[10px] text-white/28">
            {sourceRecordCount} records · {evidence.week}
          </span>
        }
      />
      {evidence.unavailable_sources.length > 0 ? (
        <div className="px-5">
          <InlineNotice
            message={`${evidence.unavailable_sources.join(
              ", ",
            )} evidence is temporarily unavailable. Available receipts remain visible; missing sources are not rendered as zero.`}
          />
        </div>
      ) : null}
      <div className="grid lg:grid-cols-3">
        <SourceEvidenceColumn
          title="Conversation · Bluesky"
          count={evidence.conversation.length}
          empty="No resolved conversation receipts for this genre and week."
        >
          {evidence.conversation.map((post) => (
            <a
              key={post.post_uri}
              href={blueskyUrl(post.post_uri, post.did)}
              target="_blank"
              rel="noreferrer"
              className="focus-ring group block border-b hairline px-5 py-4 last:border-b-0 hover:bg-white/[0.025]"
            >
              <p className="line-clamp-4 text-xs leading-5 text-white/62">
                {post.text}
              </p>
              <div className="mt-3 flex items-center justify-between gap-3">
                <span className="numeral text-[9px] text-white/27">
                  {post.likes} like · {post.reposts} repost · {post.replies}{" "}
                  reply
                </span>
                <ExternalLink
                  size={11}
                  className="text-white/20 group-hover:text-accent"
                />
              </div>
              <p className="mt-2 text-[9px] text-white/27">
                {post.artist_name_raw} · {post.resolution_method} ·{" "}
                <span className="numeral">
                  {formatNumber(post.resolution_score, 1)}
                </span>
              </p>
            </a>
          ))}
        </SourceEvidenceColumn>

        <SourceEvidenceColumn
          title="Listening change · Last.fm"
          count={evidence.listening.length}
          empty="No valid week-over-week listening changes for this genre."
          bordered
        >
          {evidence.listening.map((artist) => (
            <a
              key={`${artist.artist_key}-${artist.fetched_at}`}
              href={lastfmUrl(artist.artist_name)}
              target="_blank"
              rel="noreferrer"
              className="focus-ring group grid grid-cols-[1fr_auto] gap-4 border-b hairline px-5 py-4 last:border-b-0 hover:bg-white/[0.025]"
            >
              <div>
                <p className="text-xs text-white/70">{artist.artist_name}</p>
                <p className="mt-1 text-[9px] text-white/25">
                  {artist.artist_mbid ? "MBID join" : "name join"} ·{" "}
                  {artist.membership_method}
                </p>
              </div>
              <div className="text-right">
                <p className="numeral text-[10px] text-white/65">
                  +{artist.listeners_delta.toLocaleString("en")} listeners
                </p>
                <p className="numeral mt-1 text-[9px] text-white/30">
                  +{artist.playcount_delta.toLocaleString("en")} plays
                </p>
                <p className="numeral mt-1 text-[9px] text-white/30">
                  {artist.interval_days.toFixed(1)}-day observed window ·{" "}
                  {artist.listening_window_status === "valid_weekly"
                    ? "valid weekly"
                    : "legacy audit pending"}
                </p>
              </div>
            </a>
          ))}
        </SourceEvidenceColumn>

        <SourceEvidenceColumn
          title="Release supply · MusicBrainz"
          count={evidence.supply.length}
          empty="No first releases entered this genre during the selected week."
          bordered
        >
          {evidence.supply.map((release) => (
            <a
              key={release.release_group_mbid}
              href={musicbrainzUrl(release.release_group_mbid)}
              target="_blank"
              rel="noreferrer"
              className="focus-ring group block border-b hairline px-5 py-4 last:border-b-0 hover:bg-white/[0.025]"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs text-white/70">{release.title}</p>
                  <p className="mt-1 text-[9px] text-white/34">
                    {release.artist_credits
                      .map(
                        (credit) =>
                          `${credit.credit_name}${credit.join_phrase}`,
                      )
                      .join("") || "Unknown artist"}
                  </p>
                </div>
                <ExternalLink
                  size={11}
                  className="mt-0.5 shrink-0 text-white/20 group-hover:text-accent"
                />
              </div>
              <p className="numeral mt-3 text-[9px] text-white/26">
                {release.first_release_date} ·{" "}
                {release.types.join(" / ") || "release group"}
              </p>
              {release.genres.length > 0 ? (
                <p className="mt-2 text-[9px] text-white/24">
                  {release.genres.join(" · ")}
                </p>
              ) : null}
            </a>
          ))}
        </SourceEvidenceColumn>
      </div>
    </Panel>
  );
}

function SourceEvidenceColumn({
  title,
  count,
  empty,
  bordered = false,
  children,
}: {
  title: string;
  count: number;
  empty: string;
  bordered?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      className={bordered ? "border-t hairline lg:border-l lg:border-t-0" : ""}
    >
      <div className="flex items-center justify-between border-b hairline px-5 py-3">
        <h3 className="text-[10px] uppercase tracking-[0.12em] text-white/38">
          {title}
        </h3>
        <span className="numeral text-[9px] text-white/25">{count}</span>
      </div>
      {count > 0 ? (
        <div className="max-h-[440px] overflow-y-auto">{children}</div>
      ) : (
        <p className="px-5 py-8 text-xs leading-5 text-white/28">{empty}</p>
      )}
    </section>
  );
}
