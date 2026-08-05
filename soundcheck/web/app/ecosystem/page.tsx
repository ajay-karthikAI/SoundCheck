import { DiscoveryHealthReport } from "@/components/discovery-health-report";
import { ComparisonControl } from "@/components/taxonomy-controls";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  ScopeContext,
} from "@/components/ui";
import { getEcosystem, getMacroFamilies } from "@/lib/api";
import { readScope, scopeLabel } from "@/lib/scope";

export const dynamic = "force-dynamic";

export default async function EcosystemPage({
  searchParams,
}: {
  searchParams: { family?: string; context?: string };
}) {
  const scope = readScope(searchParams);
  const [healthResponse, familyResponse] = await Promise.all([
    getEcosystem(scope, 26),
    getMacroFamilies(),
  ]);
  const familyName = scopeLabel(
    scope,
    familyResponse.ok ? familyResponse.data.items : [],
  );
  return (
    <>
      <PageHeader
        eyebrow="Decision 04 · Protect discovery health"
        title="Is attention opening more paths to discovery—or fewer?"
        description="Measure diversity, concentration, and scene renewal inside a music family or across the full taxonomy. Every health estimate retains its uncertainty."
        action={<ComparisonControl context={scope.context} />}
      />
      <ScopeContext
        family={familyName}
        context={scope.context}
        taxonomyVersion="Taxonomy 2.0.0"
      />
      {!healthResponse.ok ? (
        <ErrorState message={healthResponse.message} />
      ) : healthResponse.data.length === 0 ? (
        <EmptyState
          title="Discovery health is not decision-ready yet"
          message="Health needs a complete week and real listening changes. Soundcheck waits for at least two Last.fm snapshots instead of inferring movement from lifetime totals."
        />
      ) : (
        <DiscoveryHealthReport weeklyHealth={healthResponse.data} />
      )}
    </>
  );
}
