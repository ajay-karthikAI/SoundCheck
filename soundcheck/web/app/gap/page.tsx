import { DemandMismatchBoard } from "@/components/demand-mismatch-board";
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
} from "@/lib/api";
import { getProvisionalObservedOpportunities } from "@/lib/provisional-api";
import { readScope, scopeLabel } from "@/lib/scope";
import { previousIsoWeeks } from "@/lib/weeks";

export const metadata = {
  title: "Unspoken demand",
};

export default async function DiscoveryGapPage({
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
    familyResponse,
  ] =
    await Promise.all([
    getOpportunities(scope),
    getProvisionalObservedOpportunities(scope),
    getCoverage(scope),
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

  return (
    <>
      <PageHeader
        eyebrow="Decision 03 · Find unspoken demand"
        title="Act on listening before it becomes consensus."
        description="When plays rise ahead of conversation, discovery can still be shaped. When conversation runs ahead of listening, validate the hype before committing creators, programming, or promotion."
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
      />
      {provisional ? (
        <InlineNotice
          message={`Showing the real observed discovery gap for ISO week ${provisionalResponse.ok ? provisionalResponse.data.week : ""}. This provisional view uses global within-week comparisons; taxonomy-v2 peer comparisons remain unavailable until the published coverage gates pass.`}
        />
      ) : null}
      {!openingResponse.ok && !provisional ? (
        <ErrorState message={openingResponse.message} />
      ) : displayedOpenings.length === 0 ? (
        <EmptyState
          title="No demand mismatch is ready to act on"
          message="Comparing listening with conversation requires consecutive Last.fm snapshots. Lifetime totals are never passed off as current demand."
          href="/methods"
          linkLabel="See why listening changes matter"
        />
      ) : (
        <DemandMismatchBoard opportunities={displayedOpenings} />
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
