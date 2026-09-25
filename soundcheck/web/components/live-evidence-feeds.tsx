import { ExternalLink, MessageCircle, Music2, TrendingUp } from "lucide-react";

import { Panel, PanelHeader, StatusPill } from "@/components/ui";
import {
  blueskyUrl,
  lastfmUrl,
  musicbrainzUrl,
} from "@/lib/format";
import type {
  ConversationReceipt,
  GenreIdentity,
  ListeningReceipt,
  SupplyReceipt,
} from "@/lib/types";

export type ConversationFeedItem = ConversationReceipt & {
  genres: GenreIdentity[];
};

export type ListeningFeedItem = ListeningReceipt & {
  genres: GenreIdentity[];
};

export type SupplyFeedItem = SupplyReceipt & {
  genres_seen_in: GenreIdentity[];
};

export function LiveEvidenceFeeds({
  conversation,
  listening,
  supply,
}: {
  conversation: ConversationFeedItem[];
  listening: ListeningFeedItem[];
  supply: SupplyFeedItem[];
}) {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <EvidenceFeed
        icon={<MessageCircle aria-hidden="true" size={14} />}
        kicker="Bluesky · Conversation"
        title="What people are discussing"
        description="Resolved public posts with direct links. Engagement is observed—not inferred—and each item retains its artist and genre-resolution trail."
        count={conversation.length}
        empty="No resolved music posts were found for this family and week."
      >
        {conversation.map((post) => (
          <a
            key={post.post_uri}
            href={blueskyUrl(post.post_uri, post.did)}
            target="_blank"
            rel="noreferrer"
            className="focus-ring group block border-b hairline px-5 py-5 last:border-b-0 hover:bg-ink/[0.025]"
          >
            <div className="flex items-start justify-between gap-4">
              <StatusPill>{post.resolution_method}</StatusPill>
              <ExternalLink
                aria-hidden="true"
                size={11}
                className="mt-1 shrink-0 text-faint group-hover:text-accent"
              />
            </div>
            <p className="mt-4 line-clamp-5 text-xs leading-5 text-muted">
              {post.text}
            </p>
            <p className="numeral mt-4 text-[9px] text-faint">
              {post.likes} like · {post.reposts} repost · {post.replies} reply
            </p>
            <GenreLine genres={post.genres} />
          </a>
        ))}
      </EvidenceFeed>

      <EvidenceFeed
        icon={<TrendingUp aria-hidden="true" size={14} />}
        kicker="Last.fm · Listening change"
        title="Who is gaining listeners"
        description="Changes between consecutive cumulative snapshots. First observations and negative source corrections never become weekly listening signals."
        count={listening.length}
        empty="No valid consecutive listening changes were found for this family."
      >
        {listening.map((artist) => (
          <a
            key={`${artist.artist_key}-${artist.fetched_at}`}
            href={lastfmUrl(artist.artist_name)}
            target="_blank"
            rel="noreferrer"
            className="focus-ring group block border-b hairline px-5 py-5 last:border-b-0 hover:bg-ink/[0.025]"
          >
            <div className="flex items-start justify-between gap-4">
              <p className="text-sm font-medium text-ink group-hover:text-ink">
                {artist.artist_name}
              </p>
              <ExternalLink
                aria-hidden="true"
                size={11}
                className="mt-1 shrink-0 text-faint group-hover:text-accent"
              />
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <ObservedChange
                label="Listeners gained"
                value={artist.listeners_delta}
              />
              <ObservedChange
                label="Plays gained"
                value={artist.playcount_delta}
              />
            </div>
            <GenreLine genres={artist.genres} />
          </a>
        ))}
      </EvidenceFeed>

      <EvidenceFeed
        icon={<Music2 aria-hidden="true" size={14} />}
        kicker="MusicBrainz · Release supply"
        title="What artists released"
        description="First-release records from MusicBrainz. Singles are song-level titles; albums and EPs remain labeled so they are not mistaken for tracks."
        count={supply.length}
        empty="No first-release records were found for this family and week."
      >
        {supply.map((release) => {
          const kind = release.types[0] ?? "Release";
          return (
            <a
              key={release.release_group_mbid}
              href={musicbrainzUrl(release.release_group_mbid)}
              target="_blank"
              rel="noreferrer"
              className="focus-ring group block border-b hairline px-5 py-5 last:border-b-0 hover:bg-ink/[0.025]"
            >
              <div className="flex items-start justify-between gap-4">
                <StatusPill
                  tone={kind.toLowerCase() === "single" ? "accent" : "neutral"}
                >
                  {kind}
                </StatusPill>
                <ExternalLink
                  aria-hidden="true"
                  size={11}
                  className="mt-1 shrink-0 text-faint group-hover:text-accent"
                />
              </div>
              <p className="mt-4 text-sm font-medium leading-5 text-ink group-hover:text-ink">
                {release.title}
              </p>
              <p className="mt-2 text-[10px] text-faint">
                {release.artist_credits
                  .map(
                    (credit) =>
                      `${credit.credit_name}${credit.join_phrase}`,
                  )
                  .join("") || "Unknown artist"}
              </p>
              <p className="numeral mt-4 text-[9px] text-faint">
                First released {release.first_release_date}
              </p>
              <GenreLine genres={release.genres_seen_in} />
            </a>
          );
        })}
      </EvidenceFeed>
    </div>
  );
}

function EvidenceFeed({
  icon,
  kicker,
  title,
  description,
  count,
  empty,
  children,
}: {
  icon: React.ReactNode;
  kicker: string;
  title: string;
  description: string;
  count: number;
  empty: string;
  children: React.ReactNode;
}) {
  return (
    <Panel className="overflow-hidden">
      <PanelHeader
        kicker={kicker}
        title={title}
        meta={
          <span className="flex items-center gap-2 text-accent">
            {icon}
            <span className="numeral text-[10px]">{count}</span>
          </span>
        }
      />
      <p className="min-h-[86px] border-b hairline px-5 py-4 text-[10px] leading-5 text-faint">
        {description}
      </p>
      {count > 0 ? (
        <div className="max-h-[760px] overflow-y-auto">{children}</div>
      ) : (
        <div className="flex min-h-48 items-center justify-center px-6 text-center">
          <p className="max-w-xs text-xs leading-5 text-faint">{empty}</p>
        </div>
      )}
    </Panel>
  );
}

function ObservedChange({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="border hairline bg-ink/[0.018] px-3 py-3">
      <p className="text-[9px] text-faint">
        {label}
      </p>
      <p className="numeral mt-2 text-sm text-ink">
        +{value.toLocaleString("en")}
      </p>
    </div>
  );
}

function GenreLine({ genres }: { genres: GenreIdentity[] }) {
  return (
    <p className="mt-4 text-[9px] text-faint">
      {genres
        .slice(0, 3)
        .map((genre) => genre.display_name)
        .join(" · ")}
    </p>
  );
}
