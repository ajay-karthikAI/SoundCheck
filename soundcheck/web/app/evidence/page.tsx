import {
  LiveEvidenceFeeds,
  type ConversationFeedItem,
  type ListeningFeedItem,
  type SupplyFeedItem,
} from "@/components/live-evidence-feeds";
import { ComparisonControl } from "@/components/taxonomy-controls";
import {
  EmptyState,
  ErrorState,
  InlineNotice,
  PageHeader,
  ScopeContext,
} from "@/components/ui";
import {
  getCoverage,
  getGenreEvidence,
  getMacroFamilies,
  getOpportunities,
} from "@/lib/api";
import { readScope, scopeLabel } from "@/lib/scope";
import type {
  GenreEvidenceBundle,
  GenreIdentity,
} from "@/lib/types";

export const metadata = {
  title: "Live evidence",
};

export const dynamic = "force-dynamic";

const GENRE_LIMIT = 8;
const ITEMS_PER_GENRE = 8;
const FEED_LIMIT = 30;

export default async function LiveEvidencePage({
  searchParams,
}: {
  searchParams: {
    week?: string;
    family?: string;
    context?: string;
  };
}) {
  const scope = readScope(searchParams);
  const [opportunityResponse, coverageResponse, familyResponse] =
    await Promise.all([
      getOpportunities(scope, GENRE_LIMIT),
      getCoverage(scope, undefined, 100),
      getMacroFamilies(),
    ]);
  const familyName = scopeLabel(
    scope,
    familyResponse.ok ? familyResponse.data.items : [],
  );
  const selectedGenres = opportunityResponse.ok
    ? opportunityResponse.data.items.map((item) => item.genre)
    : coverageResponse.ok
      ? coverageResponse.data.items
          .filter((item) => item.genre.coverage_status === "ready")
          .slice(0, GENRE_LIMIT)
          .map((item) => item.genre)
      : [];
  const evidenceResults = await Promise.all(
    selectedGenres.map((genre) =>
      getGenreEvidence(genre, scope.week, ITEMS_PER_GENRE),
    ),
  );
  const available = evidenceResults.flatMap((response) =>
    response.ok ? [response.data] : [],
  );
  const failedCount = evidenceResults.length - available.length;
  const conversation = collectConversation(available);
  const listening = collectListening(available);
  const supply = collectSupply(available);
  const allEmpty =
    conversation.length === 0 && listening.length === 0 && supply.length === 0;

  return (
    <>
      <PageHeader
        eyebrow="Source record · What is happening now?"
        title="Follow the conversation, listening changes, and releases."
        description="Three public evidence feeds show what people discuss on Bluesky, which artists gained listeners and plays between Last.fm snapshots, and which songs, EPs, and albums first appeared in MusicBrainz."
        action={<ComparisonControl context={scope.context} />}
      />
      <ScopeContext
        family={familyName}
        context={scope.context}
        taxonomyVersion="Taxonomy 2.0.0"
        readyGenres={selectedGenres.length}
        partialGenres={
          coverageResponse.ok
            ? coverageResponse.data.items.length - selectedGenres.length
            : undefined
        }
      />
      {!opportunityResponse.ok && !coverageResponse.ok ? (
        <ErrorState message={opportunityResponse.message} />
      ) : allEmpty ? (
        <EmptyState
          title="No source receipts are ready for this scope"
          message="A blank feed means the selected family has no available public receipts for this week. It does not mean zero conversation, listening, or releases."
          href="/methods"
          linkLabel="See the evidence standard"
        />
      ) : (
        <LiveEvidenceFeeds
          conversation={conversation}
          listening={listening}
          supply={supply}
        />
      )}
      {failedCount > 0 ? (
        <InlineNotice
          message={`${failedCount} genre ${
            failedCount === 1 ? "feed is" : "feeds are"
          } temporarily unavailable. Available receipts remain visible.`}
        />
      ) : null}
    </>
  );
}

function collectConversation(
  bundles: GenreEvidenceBundle[],
): ConversationFeedItem[] {
  const posts = new Map<string, ConversationFeedItem>();
  bundles.forEach((bundle) => {
    bundle.conversation.forEach((post) => {
      const existing = posts.get(post.post_uri);
      posts.set(post.post_uri, {
        ...(existing ?? post),
        genres: mergeGenres(existing?.genres ?? [], bundle.genre),
      });
    });
  });
  return [...posts.values()]
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .slice(0, FEED_LIMIT);
}

function collectListening(
  bundles: GenreEvidenceBundle[],
): ListeningFeedItem[] {
  const artists = new Map<string, ListeningFeedItem>();
  bundles.forEach((bundle) => {
    bundle.listening.forEach((artist) => {
      const existing = artists.get(artist.artist_key);
      const strongest =
        !existing ||
        artist.listeners_delta + artist.playcount_delta >
          existing.listeners_delta + existing.playcount_delta
          ? artist
          : existing;
      artists.set(artist.artist_key, {
        ...strongest,
        genres: mergeGenres(existing?.genres ?? [], bundle.genre),
      });
    });
  });
  return [...artists.values()]
    .sort(
      (left, right) =>
        right.listeners_delta +
        right.playcount_delta -
        left.listeners_delta -
        left.playcount_delta,
    )
    .slice(0, FEED_LIMIT);
}

function collectSupply(
  bundles: GenreEvidenceBundle[],
): SupplyFeedItem[] {
  const releases = new Map<string, SupplyFeedItem>();
  bundles.forEach((bundle) => {
    bundle.supply.forEach((release) => {
      const existing = releases.get(release.release_group_mbid);
      releases.set(release.release_group_mbid, {
        ...(existing ?? release),
        genres_seen_in: mergeGenres(
          existing?.genres_seen_in ?? [],
          bundle.genre,
        ),
      });
    });
  });
  return [...releases.values()]
    .sort((left, right) =>
      right.first_release_date.localeCompare(left.first_release_date),
    )
    .slice(0, FEED_LIMIT);
}

function mergeGenres(
  genres: GenreIdentity[],
  genre: GenreIdentity,
): GenreIdentity[] {
  return genres.some((item) => item.genre_id === genre.genre_id)
    ? genres
    : [...genres, genre];
}
