import { CircleDot } from "lucide-react";
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
  return (
    <div className="min-h-screen">
      <header className="border-b hairline">
        <div className="mx-auto max-w-product px-5 sm:px-8">
          <div className="flex min-h-16 flex-wrap items-center justify-between gap-4 py-3">
            <Link
              href="/"
              className="focus-ring flex items-center gap-3 rounded-sm"
              aria-label="Soundcheck home"
            >
              <span className="flex size-7 items-center justify-center rounded-md border hairline bg-white/[0.025]">
                <CircleDot
                  aria-hidden="true"
                  className="text-accent"
                  size={14}
                  strokeWidth={1.8}
                />
              </span>
              <span className="text-[13px] font-medium tracking-[-0.01em]">
                Soundcheck
              </span>
              <span className="hidden border-l hairline pl-3 text-[11px] text-white/35 sm:block">
                Music ecosystem intelligence
              </span>
            </Link>
            <div className="flex w-full items-center gap-4 sm:w-auto">
              <GenreSearchForm />
              <div className="numeral hidden text-[9px] uppercase tracking-[0.14em] text-white/25 lg:block">
                {taxonomyVersion}
              </div>
            </div>
          </div>
          <SiteNav />
          {familyNavigationUnavailable ? (
            <div className="py-3 text-[10px] text-white/28">
              Genre-family navigation is temporarily unavailable.
            </div>
          ) : (
            <MacroFamilyNavigation families={macroFamilies} />
          )}
        </div>
      </header>
      {fixtureMode ? (
        <div className="border-b border-[#8196d8]/25 bg-[#8196d8]/[0.055]">
          <div className="numeral mx-auto flex max-w-product items-center justify-between gap-4 px-5 py-2 text-[9px] uppercase tracking-[0.14em] text-[#aebbe7] sm:px-8">
            <span>Taxonomy v2 fixture preview</span>
            <span className="text-white/32">
              Product evaluation only · not observed evidence
            </span>
          </div>
        </div>
      ) : null}
      <main className="mx-auto max-w-product px-5 py-12 sm:px-8 sm:py-16">
        {children}
      </main>
      <footer className="border-t hairline">
        <div className="mx-auto flex max-w-product flex-col gap-4 px-5 py-8 text-xs text-white/35 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p>Evidence before action. Uncertainty stays visible.</p>
          <div className="flex items-center gap-5">
            <span className="numeral inline-flex items-center gap-2">
              <span
                className={`size-1.5 rounded-full ${
                  freshnessUnavailable
                    ? "bg-[#b98585]"
                    : dataThrough
                      ? "bg-accent"
                      : "bg-white/20"
                }`}
              />
              {freshnessUnavailable
                ? "Data freshness unavailable"
                : dataThrough
                  ? `${
                      fixtureMode
                        ? "Fixture data through"
                        : provisionalData
                          ? "Provisional data through"
                          : "Data through"
                    } ${formatDataThrough(dataThrough)}`
                  : "Awaiting a complete week"}
            </span>
            <Link
              href="/methods"
              className="focus-ring rounded-sm hover:text-white/75"
            >
              How it works
            </Link>
            <span className="numeral">UTC · ISO weeks</span>
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
