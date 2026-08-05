"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import type {
  ComparisonContext,
  MacroFamily,
} from "@/lib/types";

export function GenreSearchForm() {
  return (
    <form
      action="/search"
      className="relative w-full sm:w-64"
      role="search"
    >
      <Search
        aria-hidden="true"
        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/25"
        size={13}
      />
      <input
        aria-label="Search genres"
        name="q"
        type="search"
        placeholder="Search every genre"
        className="focus-ring h-9 w-full rounded-md border hairline bg-white/[0.025] pl-9 pr-3 text-xs text-white/75 placeholder:text-white/25"
      />
    </form>
  );
}

export function MacroFamilyNavigation({
  families,
}: {
  families: MacroFamily[];
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selected = searchParams.get("family") ?? "macro_rock";
  const visibleFamilies = families.filter(
    (family) => family.macro_family_id !== "macro_unclassified",
  );

  return (
    <nav
      aria-label="Macro-family navigation"
      className="flex items-center gap-1 overflow-x-auto py-3"
    >
      <FamilyLink
        href={scopeHref(pathname, searchParams, "all")}
        active={selected === "all"}
        label="All music"
      />
      {visibleFamilies.map((family) => (
        <FamilyLink
          key={family.macro_family_id}
          href={scopeHref(
            pathname,
            searchParams,
            family.macro_family_id,
          )}
          active={selected === family.macro_family_id}
          label={family.display_name}
          indieLens={family.macro_family_id === "macro_rock"}
        />
      ))}
    </nav>
  );
}

function FamilyLink({
  href,
  active,
  label,
  indieLens = false,
}: {
  href: string;
  active: boolean;
  label: string;
  indieLens?: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={`focus-ring inline-flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] ${
        active
          ? "border-accent/40 bg-accent/10 text-white"
          : "border-white/[0.07] text-white/38 hover:border-white/15 hover:text-white/70"
      }`}
    >
      {label}
      {indieLens ? (
        <span className="numeral text-[8px] uppercase tracking-[0.1em] text-accent">
          indie lens
        </span>
      ) : null}
    </Link>
  );
}

export function ComparisonControl({
  context,
}: {
  context: ComparisonContext;
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  return (
    <div
      className="inline-flex rounded-md border hairline bg-surface p-1"
      aria-label="Comparison context"
    >
      <ContextLink
        href={contextHref(pathname, searchParams, "peer_family")}
        active={context === "peer_family"}
        label="Family peers"
      />
      <ContextLink
        href={contextHref(pathname, searchParams, "global")}
        active={context === "global"}
        label="All genres"
      />
    </div>
  );
}

function ContextLink({
  href,
  active,
  label,
}: {
  href: string;
  active: boolean;
  label: string;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={`focus-ring rounded px-3 py-1.5 text-[10px] ${
        active
          ? "bg-white/[0.08] text-white"
          : "text-white/32 hover:text-white/70"
      }`}
    >
      {label}
    </Link>
  );
}

function scopeHref(
  pathname: string,
  current: { toString(): string },
  family: string,
): string {
  const query = new URLSearchParams(current.toString());
  query.set("family", family);
  query.set("context", family === "all" ? "global" : "peer_family");
  query.delete("cursor");
  return `${pathname}?${query.toString()}`;
}

function contextHref(
  pathname: string,
  current: { toString(): string },
  context: ComparisonContext,
): string {
  const query = new URLSearchParams(current.toString());
  query.set("context", context);
  if (
    context === "peer_family" &&
    (!query.get("family") || query.get("family") === "all")
  ) {
    query.set("family", "macro_rock");
  }
  query.delete("cursor");
  return `${pathname}?${query.toString()}`;
}
