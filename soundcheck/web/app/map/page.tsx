import { AdjacentScenesMap } from "@/components/adjacent-scenes-map";
import { ComparisonControl } from "@/components/taxonomy-controls";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  ScopeContext,
} from "@/components/ui";
import { getMacroFamilies, getSceneMap } from "@/lib/api";
import { readScope, scopeLabel } from "@/lib/scope";

export const dynamic = "force-dynamic";

export default async function MapPage({
  searchParams,
}: {
  searchParams: {
    family?: string;
    context?: string;
  };
}) {
  const scope = readScope(searchParams, { defaultToAllFamilies: true });
  const [sceneMapResponse, familyResponse] = await Promise.all([
    getSceneMap(scope),
    getMacroFamilies(),
  ]);
  const familyName = scopeLabel(
    scope,
    familyResponse.ok ? familyResponse.data.items : [],
  );
  return (
    <>
      <PageHeader
        eyebrow="Decision 05 · Find a differentiated direction"
        title="Explore nearby scenes without following the crowd."
        description="The taxonomy-v2 scene map groups genres into creative neighborhoods and labels every macro-family cluster. Color shows measured opportunity, size shows evidence volume, and genres that have not cleared coverage remain visibly unscored."
        action={<ComparisonControl context={scope.context} />}
      />
      <ScopeContext
        family={familyName}
        context={scope.context}
        taxonomyVersion="Taxonomy 2.0.0"
      />
      {!sceneMapResponse.ok ? (
        <ErrorState message={sceneMapResponse.message} />
      ) : sceneMapResponse.data.items.length === 0 ? (
        <EmptyState
          title="No adjacent-scene choices are ready"
          message="Soundcheck needs taxonomy-v2 genre embeddings before it can show creative neighborhoods for this family."
        />
      ) : (
        <AdjacentScenesMap points={sceneMapResponse.data.items} />
      )}
    </>
  );
}
