import { MarketOpeningsBoard } from "@/components/market-openings-board";
import { CoverageSummary } from "@/components/coverage-summary";
import { ComparisonControl } from "@/components/taxonomy-controls";
import {
  EmptyState,
  ErrorState,
  InlineNotice,
  PageHeader,
  ScopeContext,
} from "@/components/ui";
import { WeekSelector } from "@/components/week-selector";
import {
  getCoverage,
  getMacroFamilies,
  getOpportunities,
  getSceneMap,
} from "@/lib/api";
import { getProvisionalObservedOpportunities } from "@/lib/provisional-api";
import { readScope, scopeLabel } from "@/lib/scope";
import { previousIsoWeeks } from "@/lib/weeks";

export default async function MarketOpeningsPage({
  searchParams,
}: {
  searchParams: {
    week?: string;
    family?: string;
    context?: string;
  };
}) {
  const scope = readScope(searchParams);
  const [
    openingResponse,
    provisionalResponse,
    coverageResponse,
    adjacencyResponse,
    familyResponse,
  ] = await Promise.all([
    getOpportunities(scope),
    getProvisionalObservedOpportunities(scope),
    getCoverage(scope),
    getSceneMap(scope),
    getMacroFamilies(),
  ]);
  const provisionalOpenings = provisionalResponse.ok
    ? provisionalResponse.data.items
    : [];
  const provisional =
    (!openingResponse.ok || openingResponse.data.items.length === 0) &&
    provisionalOpenings.length > 0;
  const displayedOpenings = provisional
    ? provisionalOpenings
    : openingResponse.ok
      ? openingResponse.data.items
      : [];
  const decisionWeeks = coverageResponse.ok
    ? previousIsoWeeks(coverageResponse.data.week)
    : [];
  const familyName = scopeLabel(
    scope,
    familyResponse.ok ? familyResponse.data.items : [],
  );
  const readyCount = coverageResponse.ok
    ? coverageResponse.data.items.filter(
        (item) => item.genre.coverage_status === "ready",
      ).length
    : undefined;
  const partialCount = coverageResponse.ok
    ? coverageResponse.data.items.length - (readyCount ?? 0)
    : undefined;

  return (
    <>
      <PageHeader
        eyebrow="Decision 01 · Where to enter"
        title="Find scenes where audience demand has room to grow."
        description="Start with comparable genre peers, then widen to all music when the question demands it. Every opening shows its uncertainty, coverage state, and source trail."
        action={
          <div className="flex flex-wrap items-center gap-2">
            <ComparisonControl context={scope.context} />
            <WeekSelector
              availableWeeks={decisionWeeks}
              selectedWeek={scope.week}
            />
          </div>
        }
      />
      <ScopeContext
        family={familyName}
        context={provisional ? "global" : scope.context}
        taxonomyVersion="Taxonomy 2.0.0"
        readyGenres={readyCount}
        partialGenres={partialCount}
      />
      {provisional ? (
        <InlineNotice
          message={`Showing the latest complete eligible ISO week ${provisionalResponse.ok ? provisionalResponse.data.week : ""}. These are provisional global comparisons from consecutive-week Last.fm snapshots, Bluesky conversation, and MusicBrainz releases. Current partial-week evidence is not ranked.`}
        />
      ) : null}
      {!openingResponse.ok && !provisional ? (
        <ErrorState message={openingResponse.message} />
      ) : displayedOpenings.length === 0 ? (
        <EmptyState
          title="No peer-comparable opening is ready in this family"
          message="The selected genres have not yet cleared all three evidence gates. Missing listening history or unresolved artists remain explicitly unavailable rather than appearing as zero demand."
          href="/methods"
          linkLabel="See the evidence standard"
        />
      ) : (
        <>
          <MarketOpeningsBoard
            opportunities={displayedOpenings}
            sceneContext={
              provisional
                ? []
                : adjacencyResponse.ok
                  ? adjacencyResponse.data.items
                  : []
            }
          />
          {!provisional && !adjacencyResponse.ok ? (
            <InlineNotice
              message={`Evidence-volume sizing is temporarily unavailable: ${adjacencyResponse.message}`}
            />
          ) : null}
        </>
      )}
      {coverageResponse.ok ? (
        <CoverageSummary coverage={coverageResponse.data.items} />
      ) : (
        <InlineNotice
          message={`Coverage context is temporarily unavailable: ${coverageResponse.message}`}
        />
      )}
    </>
  );
}
