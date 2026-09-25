import Link from "next/link";
import type { ReactNode } from "react";

import { SiteNav } from "@/components/site-nav";
import {
  GenreSearchForm,
  MacroFamilyNavigation,
} from "@/components/taxonomy-controls";
import type { MacroFamily } from "@/lib/types";

export function SiteShell({
  children,
  dataThrough,
  freshnessUnavailable,
  fixtureMode,
  provisionalData,
  taxonomyVersion,
  macroFamilies,
  familyNavigationUnavailable,
}: {
  children: ReactNode;
  dataThrough: string | null;
  freshnessUnavailable: boolean;
  fixtureMode: boolean;
  provisionalData: boolean;
  taxonomyVersion: string;
  macroFamilies: MacroFamily[];
  familyNavigationUnavailable: boolean;
}) {
  const freshness = freshnessUnavailable
    ? "Data freshness unavailable"
    : dataThrough
      ? `${
          fixtureMode
            ? "Fixture data through"
            : provisionalData
              ? "Provisional data through"
              : "Data through"
        } ${formatDataThrough(dataThrough)}`
      : "Awaiting a complete week";

  return (
    <div className="min-h-screen">
      {fixtureMode ? (
        <div className="bg-ink text-paper">
          <p className="mx-auto max-w-product px-5 py-2 text-[12px] sm:px-8">
            <span className="font-medium">Taxonomy v2 fixture preview.</span>{" "}
            <span className="text-paper/70">
              Product evaluation only — not observed evidence.
            </span>
          </p>
        </div>
      ) : null}
      <header>
        <div className="mx-auto max-w-product px-5 sm:px-8">
          <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-5 border-b-2 border-ink pb-5 pt-8 sm:pt-10">
            <Link href="/" className="focus-ring" aria-label="Soundcheck home">
              <span className="block font-serif text-[40px] font-semibold leading-none tracking-[-0.02em] text-ink sm:text-[46px]">
                Soundcheck
              </span>
              <span className="mt-2 block text-[13px] text-muted">
                Music ecosystem intelligence
              </span>
            </Link>
            <div className="flex w-full flex-col gap-3 sm:w-auto sm:items-end">
              <p className="numeral text-[12px] text-muted">
                <span className={freshnessUnavailable ? "text-caution" : undefined}>
                  {freshness}
                </span>
                <span aria-hidden="true" className="px-2 text-rule">
                  |
                </span>
                UTC · ISO weeks
              </p>
              <GenreSearchForm />
            </div>
          </div>
          <SiteNav />
          {familyNavigationUnavailable ? (
            <p className="py-3 text-[12px] text-faint">
              Genre-family navigation is temporarily unavailable.
            </p>
          ) : (
            <MacroFamilyNavigation families={macroFamilies} />
          )}
        </div>
      </header>
      <main className="mx-auto max-w-product px-5 py-10 sm:px-8 sm:py-14">
        {children}
      </main>
      <footer className="mx-auto max-w-product px-5 sm:px-8">
        <div className="flex flex-col gap-3 border-t-2 border-ink py-8 text-[13px] text-muted sm:flex-row sm:items-baseline sm:justify-between">
          <p className="font-serif text-[16px] italic text-ink">
            Evidence before action. Uncertainty stays visible.
          </p>
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
            <Link
              href="/methods"
              className="focus-ring underline decoration-rule underline-offset-4 hover:text-ink hover:decoration-ink"
            >
              How it works
            </Link>
            <span className="numeral">Taxonomy {taxonomyVersion}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

function formatDataThrough(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}
