import { notFound } from "next/navigation";

import { DecisionEvidence } from "@/components/decision-evidence";
import {
  ForecastDecisionRecord,
  SceneDecisionHistory,
} from "@/components/scene-decision-history";
import { ComparisonControl } from "@/components/taxonomy-controls";
import {
  CoverageBadge,
  CoverageExplanation,
  EmptyState,
  ErrorState,
  PageHeader,
  ScopeContext,
} from "@/components/ui";
import {
  getGenreEvidence,
  getGenreTimeseries,
  resolveGenreRoute,
} from "@/lib/api";
import type { ComparisonContext } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function GenrePage({
  params,
  searchParams,
}: {
  params: { slug: string };
  searchParams: { context?: string };
}) {
  const identityResponse = await resolveGenreRoute(params.slug);
  if (!identityResponse.ok) notFound();
  const genre = identityResponse.data;
  const context: ComparisonContext =
    searchParams.context === "global" ? "global" : "peer_family";
  const timeseriesResponse = await getGenreTimeseries(
    genre.genre_id,
    context,
  );
  if (!timeseriesResponse.ok) {
    return (
      <>
        <PageHeader
          eyebrow="Genre decision record · Taxonomy 2.0.0"
          title={genre.display_name}
          description="What changed, what may move next, and which source records support the decision."
          action={<ComparisonControl context={context} />}
        />
        <ErrorState message={timeseriesResponse.message} />
      </>
    );
  }

  const latestWeek = timeseriesResponse.data.history.at(-1)?.week;
  const evidenceResponse = await getGenreEvidence(
    genre,
    latestWeek,
  );
  const historyReady = timeseriesResponse.data.history.some(
    (point) => point.opportunity,
  );

  return (
    <>
      <PageHeader
        eyebrow="Genre decision record · Taxonomy 2.0.0"
        title={`What is driving ${genre.display_name}—and is the opening durable?`}
        description="Compare music conversation, week-over-week listening change, and release supply against the right peers. Then inspect the validated call and every public receipt behind it."
        action={
          <div className="flex flex-wrap items-center justify-end gap-3">
            <CoverageBadge status={genre.coverage_status} />
            <ComparisonControl context={context} />
          </div>
        }
      />
      <ScopeContext
        family={genre.macro_family_name}
        context={context}
        taxonomyVersion={`Taxonomy ${genre.taxonomy_version}`}
      />
      <div className="space-y-6">
        <CoverageExplanation status={genre.coverage_status} />
        {historyReady ? (
          <SceneDecisionHistory timeseries={timeseriesResponse.data} />
        ) : (
          <EmptyState
            title="This genre is known, but no estimate is ready"
            message="The current evidence does not clear the cross-source gate. Missing evidence stays missing; Soundcheck does not turn it into zero activity."
          />
        )}
        <ForecastDecisionRecord
          forecasts={timeseriesResponse.data.forecasts}
        />
        {evidenceResponse.ok ? (
          <DecisionEvidence evidence={evidenceResponse.data} />
        ) : (
          <ErrorState
            title="The public source records could not be loaded"
            message={evidenceResponse.message}
          />
        )}
      </div>
    </>
  );
}
