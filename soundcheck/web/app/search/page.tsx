import Link from "next/link";

import {
  CoverageBadge,
  CoverageExplanation,
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
} from "@/components/ui";
import { searchGenres } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: {
    q?: string;
    family?: string;
  };
}) {
  const query = searchParams.q?.trim() ?? "";
  const family =
    searchParams.family && searchParams.family !== "all"
      ? searchParams.family
      : undefined;
  const response = query
    ? await searchGenres(query, { macroFamilyId: family, limit: 50 })
    : { ok: true as const, data: { items: [], page: { next_cursor: null, has_more: false } } };

  return (
    <>
      <PageHeader
        eyebrow="Taxonomy 2.0.0 · Genre search"
        title={query ? `Search results for “${query}”` : "Find a genre by name."}
        description="Search resolves stable taxonomy-v2 genre IDs and slugs while preserving familiar genre URLs. Coverage status travels with every result."
      />
      {!response.ok ? (
        <ErrorState message={response.message} />
      ) : response.data.items.length === 0 ? (
        <EmptyState
          title={query ? "No genre matches this search" : "Start with the search field above"}
          message={
            query
              ? "Try a broader spelling or choose another macro family. Soundcheck keeps unresolved and unsupported genres explicit rather than forcing a match."
              : "Search by genre name, stable slug, or taxonomy ID."
          }
        />
      ) : (
        <Panel className="overflow-hidden">
          <div className="divide-y divide-white/[0.06]">
            {response.data.items.map((genre) => (
              <div
                key={genre.genre_id}
                className="grid gap-4 px-5 py-5 sm:grid-cols-[1fr_auto] sm:items-center sm:px-6"
              >
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <Link
                      href={`/genre/${genre.slug}`}
                      className="focus-ring text-sm font-medium text-ink hover:text-ink"
                    >
                      {genre.display_name}
                    </Link>
                    <CoverageBadge status={genre.coverage_status} />
                  </div>
                  <p className="mt-2 text-[10px] text-faint">
                    {genre.macro_family_name} ·{" "}
                    <span className="numeral">{genre.genre_id}</span>
                  </p>
                </div>
                <p className="numeral text-[9px] text-faint">
                  taxonomy {genre.taxonomy_version}
                </p>
                {genre.coverage_status !== "ready" ? (
                  <div className="sm:col-span-2">
                    <CoverageExplanation
                      status={genre.coverage_status}
                      compact
                    />
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </Panel>
      )}
    </>
  );
}
