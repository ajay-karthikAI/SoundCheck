import "server-only";

import {
  getTaxonomy,
  isFixtureMode,
  TAXONOMY_VERSION,
} from "@/lib/api";
import type {
  ApiError,
  ApiResult,
  OpportunityItem,
  OpportunityPage,
  ScopeSelection,
} from "@/lib/types";

type ObservedFreshness = {
  latest_metric_week: string | null;
  latest_complete_week: string | null;
};

type V1OpportunityRow = {
  week: string;
  genre: string;
  opportunity: { value: number; lower: number; upper: number };
  discovery_gap: { value: number; lower: number; upper: number };
  z_conversation: { value: number; lower: number; upper: number };
  z_listening: { value: number; lower: number; upper: number };
  z_supply: { value: number; lower: number; upper: number };
  shrinkage_weight: { conversation: number; supply: number };
  effective_n: { conversation: number; supply: number };
  spike_flag: {
    conversation: boolean;
    listening: boolean;
    supply: boolean;
  };
  breakout_flag: boolean;
};

const API_BASE_URL =
  process.env.SOUNDCHECK_API_URL ?? "http://127.0.0.1:8000";

/**
 * Surface the newest observed v1 metrics while taxonomy-v2 eligibility is
 * still collecting history. These are real week-over-week Last.fm deltas,
 * never lifetime totals, and remain explicitly labelled provisional in the
 * UI. This adapter does not relax or mutate any v2 coverage state.
 */
export async function getProvisionalObservedOpportunities(
  scope: ScopeSelection,
  limit = 100,
): Promise<ApiResult<OpportunityPage>> {
  if (isFixtureMode()) return emptyOpportunityPage();

  const health = await getObservedFreshness();
  if (!health.ok) return health;
  const week = scope.week ?? health.data.latest_metric_week;
  if (!week) return emptyOpportunityPage();

  const [rows, taxonomy] = await Promise.all([
    readObservedData<V1OpportunityRow[]>(
      withQuery("/api/genres/opportunities", { week, limit }),
    ),
    getTaxonomy({ macroFamilyId: scope.macroFamilyId, limit: 200 }),
  ]);
  if (!rows.ok) return rows;
  if (!taxonomy.ok) return taxonomy;

  const identities = new Map(
    taxonomy.data.genres.items.map((genre) => [
      normalizeGenreLabel(genre.display_name),
      genre,
    ]),
  );
  const items = rows.data.flatMap((row): OpportunityItem[] => {
    const genre = identities.get(normalizeGenreLabel(row.genre));
    if (!genre) return [];
    return [
      {
        genre,
        week: row.week,
        context: "global",
        estimate_status: "provisional_observed_v1",
        opportunity: row.opportunity,
        discovery_gap: row.discovery_gap,
        conversation: row.z_conversation,
        listening: row.z_listening,
        supply: row.z_supply,
        diagnostics: {
          conversation_effective_n: row.effective_n.conversation,
          listening_effective_n: null,
          supply_effective_n: row.effective_n.supply,
          conversation_shrinkage_weight:
            row.shrinkage_weight.conversation,
          listening_shrinkage_weight: null,
          supply_shrinkage_weight: row.shrinkage_weight.supply,
        },
        spike_flags: row.spike_flag,
        breakout_flag: row.breakout_flag,
      },
    ];
  });

  return {
    ok: true,
    data: {
      taxonomy_version: TAXONOMY_VERSION,
      week,
      context: "global",
      items,
      page: { next_cursor: null, has_more: false },
    },
  };
}

export function getObservedFreshness(): Promise<
  ApiResult<ObservedFreshness>
> {
  if (isFixtureMode()) {
    return Promise.resolve({
      ok: true,
      data: { latest_metric_week: null, latest_complete_week: null },
    });
  }
  return readObservedData<ObservedFreshness>("/api/health");
}

async function readObservedData<T>(path: string): Promise<ApiResult<T>> {
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
      message: "The current observed signal could not be loaded.",
    };
  }
}

function emptyOpportunityPage(): ApiResult<OpportunityPage> {
  return {
    ok: true,
    data: {
      taxonomy_version: TAXONOMY_VERSION,
      week: null,
      context: "global",
      items: [],
      page: { next_cursor: null, has_more: false },
    },
  };
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

function normalizeGenreLabel(value: string): string {
  return value
    .normalize("NFKD")
    .toLowerCase()
    .replaceAll("&", " and ")
    .replace(/[^a-z0-9]+/g, "")
    .trim();
}
