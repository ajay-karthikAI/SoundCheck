import "server-only";

import fixtureJson from "@/data/v2-fixture-api.json";
import type {
  ApiError,
  ApiResult,
  ComparisonContext,
  CoveragePage,
  CoverageStatus,
  CreatorBriefPage,
  EcosystemPoint,
  EvidencePage,
  EvidenceSource,
  ForecastPage,
  GenreCatalogPage,
  GenreEvidenceBundle,
  GenreIdentity,
  GenreTimeseries,
  MacroFamilyPage,
  NextUpPage,
  OpportunityPage,
  SceneMapPage,
  ScopeSelection,
  TaxonomyResponse,
} from "@/lib/types";

type FixtureData = {
  metadata: {
    data_mode: "taxonomy_v2_fixture";
    note: string;
    default_family_id: string;
  };
  taxonomy: TaxonomyResponse;
  macro_families: MacroFamilyPage;
  opportunities: OpportunityPage;
  histories: Record<string, GenreTimeseries>;
  evidence: Record<
    string,
    Record<EvidenceSource, EvidencePage>
  >;
  forecasts: ForecastPage;
  next_up: NextUpPage;
  ecosystem: EcosystemPoint[];
  briefs: CreatorBriefPage;
  scene_map: SceneMapPage;
  coverage: CoveragePage;
};

const fixture = fixtureJson as unknown as FixtureData;
const API_BASE_URL =
  process.env.SOUNDCHECK_API_URL ?? "http://127.0.0.1:8000";
const dataMode = process.env.SOUNDCHECK_DATA_MODE;
const useFixture =
  dataMode === "taxonomy_v2_fixture" || dataMode === "synthetic_demo";

export const DEFAULT_MACRO_FAMILY_ID = "macro_rock";
export const TAXONOMY_VERSION = "2.0.0";

function fixtureResult<T>(data: T): ApiResult<T> {
  return { ok: true, data };
}

async function readProductData<T>(path: string): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: "application/json" },
      next: { revalidate: 60 },
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as
        | ApiError
        | null;
      return {
        ok: false,
        code: payload?.detail.code ?? `http_${response.status}`,
        message:
          payload?.detail.message ??
          `Soundcheck API returned ${response.status}.`,
      };
    }
    return { ok: true, data: (await response.json()) as T };
  } catch {
    return {
      ok: false,
      code: "api_unavailable",
      message:
        "The Soundcheck evidence service is unavailable. Try again after the next data refresh.",
    };
  }
}

function withQuery(
  path: string,
  params: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  });
  const suffix = search.toString();
  return suffix ? `${path}?${suffix}` : path;
}

function scopeParams(
  scope: ScopeSelection,
): Record<string, string | undefined> {
  return {
    taxonomy_version: TAXONOMY_VERSION,
    macro_family_id: scope.macroFamilyId,
    context: scope.context,
    week: scope.week,
  };
}

export function isFixtureMode(): boolean {
  return useFixture;
}

export const getMacroFamilies = (): Promise<ApiResult<MacroFamilyPage>> =>
  useFixture
    ? Promise.resolve(fixtureResult(fixture.macro_families))
    : readProductData<MacroFamilyPage>(
        withQuery("/api/v2/macro-families", {
          taxonomy_version: TAXONOMY_VERSION,
          limit: 100,
        }),
      );

export function getTaxonomy(options?: {
  macroFamilyId?: string;
  parentGenreId?: string;
  eligibilityState?: CoverageStatus;
  limit?: number;
}): Promise<ApiResult<TaxonomyResponse>> {
  if (useFixture) {
    const items = fixture.taxonomy.genres.items.filter(
      (genre) =>
        (!options?.macroFamilyId ||
          genre.macro_family_id === options.macroFamilyId) &&
        (!options?.parentGenreId ||
          genre.parent_genre_id === options.parentGenreId) &&
        (!options?.eligibilityState ||
          genre.coverage_status === options.eligibilityState),
    );
    return Promise.resolve(
      fixtureResult({
        ...fixture.taxonomy,
        genres: {
          items: items.slice(0, options?.limit ?? 200),
          page: { next_cursor: null, has_more: false },
        },
      }),
    );
  }
  return readProductData<TaxonomyResponse>(
    withQuery("/api/v2/taxonomy", {
      taxonomy_version: TAXONOMY_VERSION,
      macro_family_id: options?.macroFamilyId,
      parent_genre_id: options?.parentGenreId,
      eligibility_state: options?.eligibilityState,
      limit: options?.limit ?? 200,
    }),
  );
}

export function searchGenres(
  query: string,
  options?: {
    macroFamilyId?: string;
    eligibilityState?: CoverageStatus;
    limit?: number;
  },
): Promise<ApiResult<GenreCatalogPage>> {
  if (useFixture) {
    const normalized = normalizeSearch(query);
    const items = fixture.taxonomy.genres.items
      .filter(
        (genre) =>
          (!options?.macroFamilyId ||
            genre.macro_family_id === options.macroFamilyId) &&
          (!options?.eligibilityState ||
            genre.coverage_status === options.eligibilityState) &&
          [genre.display_name, genre.slug, genre.genre_id].some((value) =>
            normalizeSearch(value).includes(normalized),
          ),
      )
      .slice(0, options?.limit ?? 50);
    return Promise.resolve(
      fixtureResult({
        items,
        page: { next_cursor: null, has_more: false },
      }),
    );
  }
  return readProductData<GenreCatalogPage>(
    withQuery("/api/v2/genres/search", {
      q: query,
      taxonomy_version: TAXONOMY_VERSION,
      macro_family_id: options?.macroFamilyId,
      eligibility_state: options?.eligibilityState,
      limit: options?.limit ?? 50,
    }),
  );
}

export async function resolveGenreRoute(
  routeValue: string,
): Promise<ApiResult<GenreIdentity>> {
  const decoded = decodeURIComponent(routeValue);
  const response = await searchGenres(decoded.replaceAll("-", " "), {
    limit: 50,
  });
  if (!response.ok) return response;
  const normalized = normalizeSearch(decoded);
  const match =
    response.data.items.find(
      (genre) =>
        normalizeSearch(genre.slug) === normalized ||
        normalizeSearch(genre.genre_id) === normalized ||
        normalizeSearch(genre.display_name) === normalized,
    ) ?? response.data.items[0];
  return match
    ? { ok: true, data: match }
    : {
        ok: false,
        code: "unknown_genre_id",
        message: `No taxonomy-v2 genre matches “${decoded}”.`,
      };
}

export function getOpportunities(
  scope: ScopeSelection,
  limit = 100,
): Promise<ApiResult<OpportunityPage>> {
  if (useFixture) {
    const items = fixture.opportunities.items
      .filter(
        (item) =>
          (!scope.macroFamilyId ||
            item.genre.macro_family_id === scope.macroFamilyId) &&
          item.genre.coverage_status === "ready",
      )
      .slice(0, limit)
      .map((item) => ({ ...item, context: scope.context }));
    return Promise.resolve(
      fixtureResult({
        ...fixture.opportunities,
        context: scope.context,
        items,
      }),
    );
  }
  return readProductData<OpportunityPage>(
    withQuery("/api/v2/opportunities", {
      ...scopeParams(scope),
      eligibility_state: "ready",
      limit,
    }),
  );
}

export function getCoverage(
  scope: Pick<ScopeSelection, "macroFamilyId" | "week">,
  eligibilityState?: CoverageStatus,
  limit = 200,
): Promise<ApiResult<CoveragePage>> {
  if (useFixture) {
    const items = fixture.coverage.items
      .filter(
        (item) =>
          (!scope.macroFamilyId ||
            item.genre.macro_family_id === scope.macroFamilyId) &&
          (!eligibilityState ||
            item.genre.coverage_status === eligibilityState),
      )
      .slice(0, limit);
    return Promise.resolve(
      fixtureResult({ ...fixture.coverage, items }),
    );
  }
  return readProductData<CoveragePage>(
    withQuery("/api/v2/coverage", {
      taxonomy_version: TAXONOMY_VERSION,
      macro_family_id: scope.macroFamilyId,
      week: scope.week,
      eligibility_state: eligibilityState,
      limit,
    }),
  );
}

export function getGenreTimeseries(
  genreId: string,
  context: ComparisonContext,
  weeks = 26,
): Promise<ApiResult<GenreTimeseries>> {
  if (useFixture) {
    const history = fixture.histories[genreId];
    if (!history) {
      return Promise.resolve({
        ok: false,
        code: "unknown_genre_id",
        message: `Unknown genre_id: ${genreId}`,
      });
    }
    return Promise.resolve(
      fixtureResult({
        ...history,
        context,
        history: history.history.slice(-weeks),
        forecasts: history.forecasts.map((forecast) => ({
          ...forecast,
          context,
        })),
      }),
    );
  }
  return readProductData<GenreTimeseries>(
    withQuery(
      `/api/v2/genres/${encodeURIComponent(genreId)}/timeseries`,
      {
        taxonomy_version: TAXONOMY_VERSION,
        context,
        weeks,
      },
    ),
  );
}

export function getEvidencePage(
  genreId: string,
  source: EvidenceSource,
  week?: string,
  limit = 20,
): Promise<ApiResult<EvidencePage>> {
  if (useFixture) {
    const page = fixture.evidence[genreId]?.[source];
    if (!page) {
      return Promise.resolve({
        ok: false,
        code: "unknown_genre_id",
        message: `No fixture evidence exists for ${genreId}.`,
      });
    }
    return Promise.resolve(
      fixtureResult({
        ...page,
        items: page.items.slice(0, limit),
      }),
    );
  }
  return readProductData<EvidencePage>(
    withQuery(
      `/api/v2/genres/${encodeURIComponent(genreId)}/evidence`,
      {
        taxonomy_version: TAXONOMY_VERSION,
        source,
        week,
        limit,
      },
    ),
  );
}

export async function getGenreEvidence(
  genre: GenreIdentity,
  week?: string,
  limit = 20,
): Promise<ApiResult<GenreEvidenceBundle>> {
  const sources: EvidenceSource[] = [
    "conversation",
    "listening",
    "supply",
  ];
  const results = await Promise.all(
    sources.map((source) =>
      getEvidencePage(genre.genre_id, source, week, limit),
    ),
  );
  const successful = results.filter(
    (result): result is { ok: true; data: EvidencePage } => result.ok,
  );
  if (successful.length === 0) {
    const firstFailure = results.find((result) => !result.ok);
    return {
      ok: false,
      code: firstFailure?.code ?? "evidence_unavailable",
      message:
        firstFailure?.message ??
        "No source evidence is currently available.",
    };
  }
  const bySource = new Map(
    successful.map((result) => [result.data.source, result.data]),
  );
  return {
    ok: true,
    data: {
      genre,
      week: successful[0]?.data.week ?? week ?? "",
      conversation: (bySource.get("conversation")?.items ?? []).filter(
        (item) => item.source === "conversation",
      ),
      listening: (bySource.get("listening")?.items ?? []).filter(
        (item) => item.source === "listening",
      ),
      supply: (bySource.get("supply")?.items ?? []).filter(
        (item) => item.source === "supply",
      ),
      unavailable_sources: sources.filter(
        (source) => !bySource.has(source),
      ),
    },
  };
}

export function getForecasts(
  scope: ScopeSelection,
  limit = 100,
): Promise<ApiResult<ForecastPage>> {
  if (useFixture) {
    const items = fixture.forecasts.items
      .filter(
        (item) =>
          !scope.macroFamilyId ||
          item.genre.macro_family_id === scope.macroFamilyId,
      )
      .slice(0, limit)
      .map((item) => ({ ...item, context: scope.context }));
    return Promise.resolve(
      fixtureResult({
        ...fixture.forecasts,
        context: scope.context,
        items,
      }),
    );
  }
  return readProductData<ForecastPage>(
    withQuery("/api/v2/forecasts", {
      ...scopeParams(scope),
      limit,
    }),
  );
}

export function getNextUp(
  scope: ScopeSelection,
  limit = 20,
): Promise<ApiResult<NextUpPage>> {
  if (useFixture) {
    const items = fixture.next_up.items
      .filter(
        (item) =>
          !scope.macroFamilyId ||
          item.genre.macro_family_id === scope.macroFamilyId,
      )
      .slice(0, limit)
      .map((item) => ({ ...item, context: scope.context }));
    return Promise.resolve(
      fixtureResult({
        ...fixture.next_up,
        context: scope.context,
        items,
      }),
    );
  }
  return readProductData<NextUpPage>(
    withQuery("/api/v2/forecast/next-up", {
      ...scopeParams(scope),
      eligibility_state: "ready",
      limit,
    }),
  );
}

export function getEcosystem(
  scope: ScopeSelection,
  weeks = 26,
): Promise<ApiResult<EcosystemPoint[]>> {
  if (useFixture) {
    const items = fixture.ecosystem
      .filter(
        (item) =>
          item.context === scope.context &&
          (scope.context === "global"
            ? item.macro_family_id === null
            : item.macro_family_id === scope.macroFamilyId),
      )
      .slice(-weeks);
    return Promise.resolve(fixtureResult(items));
  }
  return readProductData<EcosystemPoint[]>(
    withQuery("/api/v2/ecosystem", {
      taxonomy_version: TAXONOMY_VERSION,
      macro_family_id: scope.macroFamilyId,
      context: scope.context,
      weeks,
    }),
  );
}

export function getBriefs(
  scope: ScopeSelection,
  limit = 50,
): Promise<ApiResult<CreatorBriefPage>> {
  if (useFixture) {
    const items = fixture.briefs.items
      .filter(
        (item) =>
          !scope.macroFamilyId ||
          item.genre.macro_family_id === scope.macroFamilyId,
      )
      .slice(0, limit)
      .map((item) => ({ ...item, context: scope.context }));
    return Promise.resolve(
      fixtureResult({
        ...fixture.briefs,
        context: scope.context,
        items,
      }),
    );
  }
  return readProductData<CreatorBriefPage>(
    withQuery("/api/v2/briefs", {
      ...scopeParams(scope),
      eligibility_state: "ready",
      limit,
    }),
  );
}

export function getSceneMap(
  scope: ScopeSelection,
  limit = 200,
): Promise<ApiResult<SceneMapPage>> {
  if (useFixture) {
    const items = fixture.scene_map.items
      .filter(
        (item) =>
          !scope.macroFamilyId ||
          item.genre.macro_family_id === scope.macroFamilyId,
      )
      .slice(0, limit)
      .map((item) => ({ ...item, context: scope.context }));
    return Promise.resolve(
      fixtureResult({
        ...fixture.scene_map,
        context: scope.context,
        items,
      }),
    );
  }
  return readProductData<SceneMapPage>(
    withQuery("/api/v2/scene-map", {
      ...scopeParams(scope),
      limit,
    }),
  );
}

function normalizeSearch(value: string): string {
  return value
    .normalize("NFKD")
    .toLowerCase()
    .replaceAll("&", " and ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}
