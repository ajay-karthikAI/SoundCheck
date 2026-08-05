import type {
  ComparisonContext,
  MacroFamily,
  ScopeSelection,
} from "@/lib/types";

const DEFAULT_MACRO_FAMILY_ID = "macro_rock";
const TAXONOMY_VERSION = "2.0.0";

export type WebSearchParams = {
  family?: string;
  context?: string;
  week?: string;
};

export function readScope(
  params: WebSearchParams,
  options?: { defaultToAllFamilies?: boolean },
): ScopeSelection {
  const allFamilies =
    params.family === "all" || options?.defaultToAllFamilies === true;
  const macroFamilyId = allFamilies
    ? undefined
    : params.family || DEFAULT_MACRO_FAMILY_ID;
  const context: ComparisonContext =
    params.context === "global" || allFamilies
      ? "global"
      : "peer_family";
  return {
    macroFamilyId,
    context,
    week: params.week,
  };
}

export function scopeLabel(
  scope: ScopeSelection,
  families: MacroFamily[],
): string {
  if (!scope.macroFamilyId) return "All music";
  return (
    families.find(
      (family) => family.macro_family_id === scope.macroFamilyId,
    )?.display_name ?? scope.macroFamilyId
  );
}

export function contextLabel(context: ComparisonContext): string {
  return context === "peer_family"
    ? "Compared with family peers"
    : "Compared across all eligible genres";
}

export function taxonomyLabel(): string {
  return `Taxonomy ${TAXONOMY_VERSION}`;
}
