import { CreatorMovesFeed } from "@/components/creator-moves-feed";
import { ComparisonControl } from "@/components/taxonomy-controls";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  ScopeContext,
} from "@/components/ui";
import { getBriefs, getMacroFamilies } from "@/lib/api";
import { readScope, scopeLabel } from "@/lib/scope";

export default async function BriefsPage({
  searchParams,
}: {
  searchParams: {
    week?: string;
    family?: string;
    context?: string;
  };
}) {
  const scope = readScope(searchParams);
  const [creatorMovesResponse, familyResponse] = await Promise.all([
    getBriefs(scope),
    getMacroFamilies(),
  ]);
  const familyName = scopeLabel(
    scope,
    familyResponse.ok ? familyResponse.data.items : [],
  );
  return (
    <>
      <PageHeader
        eyebrow="Decision 06 · What should a creator make?"
        title="Turn an underserved scene into a differentiated creative move."
        description="Each note converts a measured market opening into an evidence-backed direction: which artists are rising, what listeners are saying, how quickly releases are arriving, and which crowded neighbors to avoid."
        action={<ComparisonControl context={scope.context} />}
      />
      <ScopeContext
        family={familyName}
        context={scope.context}
        taxonomyVersion="Taxonomy 2.0.0"
      />
      {!creatorMovesResponse.ok ? (
        <ErrorState message={creatorMovesResponse.message} />
      ) : creatorMovesResponse.data.items.length === 0 ? (
        <EmptyState
          title="No creator move clears the evidence gate this week"
          message="Soundcheck suppresses thin recommendations. A move publishes only when an opening has enough evidence, a positive forward call, rising reference artists, and a differentiated angle."
          href="/next-up"
          linkLabel="Review next-week calls"
        />
      ) : (
        <CreatorMovesFeed briefs={creatorMovesResponse.data.items} />
      )}
    </>
  );
}
