import {
  ForecastReadiness,
  ForecastIssueSummary,
  NextWeekCalls,
  PredictionIntervalExplainer,
} from "@/components/next-week-calls";
import { ComparisonControl } from "@/components/taxonomy-controls";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  ScopeContext,
} from "@/components/ui";
import {
  getForecasts,
  getMacroFamilies,
  getNextUp,
} from "@/lib/api";
import { readScope, scopeLabel } from "@/lib/scope";

export const metadata = {
  title: "Next week",
};

export const dynamic = "force-dynamic";

export default async function NextUpPage({
  searchParams,
}: {
  searchParams: { family?: string; context?: string };
}) {
  const scope = readScope(searchParams);
  const [nextWeekResponse, forecastResponse, familyResponse] =
    await Promise.all([
      getNextUp(scope),
      getForecasts(scope),
      getMacroFamilies(),
    ]);
  const familyName = scopeLabel(
    scope,
    familyResponse.ok ? familyResponse.data.items : [],
  );

  return (
    <>
      <div className="mb-8 border-b hairline pb-8">
        <PageHeader
          eyebrow="Decision 02 · What to watch next"
          title="Choose which emerging scenes deserve attention next week."
          description="These are forward calls on quiet risers—not a recap. A scene only leads when its momentum clears the breakout gate, and every call carries a calibrated range and held-out error."
          action={
            nextWeekResponse.ok && nextWeekResponse.data.items[0] ? (
              <ForecastIssueSummary
                call={nextWeekResponse.data.items[0]}
                count={nextWeekResponse.data.items.length}
              />
            ) : undefined
          }
        />
        <div className="-mt-3 grid gap-px overflow-hidden border hairline bg-ink/[0.08] sm:grid-cols-3">
          {[
            ["Eligibility", "Quiet-riser evidence"],
            ["Evidence bar", "Beats persistence"],
            ["Fallback", "Baseline stays visible"],
          ].map(([label, value]) => (
            <div key={label} className="bg-surface px-5 py-4">
              <p className="numeral text-[9px] text-faint">
                {label}
              </p>
              <p className="mt-1 text-xs text-muted">{value}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="-mt-4 mb-6 flex flex-wrap items-center justify-between gap-3">
        <ScopeContext
          family={familyName}
          context={scope.context}
          taxonomyVersion="Taxonomy 2.0.0"
        />
        <ComparisonControl context={scope.context} />
      </div>

      {!nextWeekResponse.ok ? (
        <ErrorState message={nextWeekResponse.message} />
      ) : nextWeekResponse.data.items.length === 0 ? (
        <EmptyState
          title="No next-week call has cleared the evidence bar"
          message="Soundcheck needs at least eight valid weeks inside the selected family. Insufficient history means the product makes no forward claim—not that movement is zero."
          href="/methods"
          linkLabel="See how calls earn publication"
        />
      ) : (
        <div className="space-y-6">
          <NextWeekCalls calls={nextWeekResponse.data.items} />
          <PredictionIntervalExplainer />
        </div>
      )}
      {forecastResponse.ok ? (
        <ForecastReadiness forecasts={forecastResponse.data.items} />
      ) : null}
    </>
  );
}
