"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import type {
  ComparisonContext,
  MacroFamily,
} from "@/lib/types";

export function GenreSearchForm() {
  return (
    <form action="/search" className="w-full sm:w-64" role="search">
      <input
        aria-label="Search genres"
        name="q"
        type="search"
        placeholder="Search every genre"
        className="focus-ring h-9 w-full border-0 border-b border-ink/30 bg-transparent px-0 text-[14px] text-ink placeholder:text-faint hover:border-ink focus:border-ink"
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
      className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5 py-3 text-[12px]"
    >
      <span className="shrink-0 text-faint">Lens</span>
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
      className={`focus-ring shrink-0 whitespace-nowrap ${
        active ? "font-medium text-ink" : "text-muted hover:text-ink"
      }`}
    >
      <span className={active ? "border-b-2 border-accent pb-0.5" : undefined}>
        {label}
      </span>
      {indieLens ? (
        <span className="ml-1.5 font-serif italic text-accent">indie lens</span>
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
      role="group"
      aria-label="Comparison context"
      className="inline-flex items-baseline gap-2.5 text-[13px]"
    >
      <span className="text-faint">Compare with</span>
      <ContextLink
        href={contextHref(pathname, searchParams, "peer_family")}
        active={context === "peer_family"}
        label="Family peers"
      />
      <span aria-hidden="true" className="text-rule">
        /
      </span>
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
      className={`focus-ring ${
        active
          ? "border-b-2 border-accent pb-0.5 font-medium text-ink"
          : "text-muted hover:text-ink"
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
