import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { ReactNode } from "react";

import { SiteShell } from "@/components/site-shell";
import {
  getCoverage,
  getMacroFamilies,
  isFixtureMode,
  TAXONOMY_VERSION,
} from "@/lib/api";
import { getObservedFreshness } from "@/lib/provisional-api";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.SOUNDCHECK_WEB_URL ?? "http://localhost:3000",
  ),
  title: {
    default: "Soundcheck — Creator decision intelligence",
    template: "%s — Soundcheck",
  },
  description:
    "Decide where audience demand has room to grow, what may move next week, and which creative direction is backed by evidence.",
  openGraph: {
    title: "Soundcheck — Creator decision intelligence",
    description:
      "Turn conversation, listening, and release evidence into market openings, next-week calls, and creator moves.",
    type: "website",
    images: [
      {
        url: "/og-v2.png",
        width: 1200,
        height: 630,
        alt: "Soundcheck signal streams converging into a weekly trend field",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Soundcheck — Creator decision intelligence",
    description:
      "Turn conversation, listening, and release evidence into market openings, next-week calls, and creator moves.",
    images: ["/og-v2.png"],
  },
};

export const dynamic = "force-dynamic";

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  const [familyResponse, coverageResponse, freshnessResponse] =
    await Promise.all([
    getMacroFamilies(),
    getCoverage({}, undefined, 1),
    getObservedFreshness(),
  ]);
  const dataThrough = coverageResponse.ok && coverageResponse.data.week
    ? coverageResponse.data.week
    : freshnessResponse.ok
      ? freshnessResponse.data.latest_metric_week
      : null;
  const provisionalData =
    !isFixtureMode() &&
    freshnessResponse.ok &&
    freshnessResponse.data.latest_metric_week !== null &&
    freshnessResponse.data.latest_complete_week === null;
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body>
        <SiteShell
          dataThrough={dataThrough}
          freshnessUnavailable={
            !coverageResponse.ok && !freshnessResponse.ok
          }
          fixtureMode={isFixtureMode()}
          provisionalData={provisionalData}
          taxonomyVersion={TAXONOMY_VERSION}
          macroFamilies={
            familyResponse.ok ? familyResponse.data.items : []
          }
          familyNavigationUnavailable={!familyResponse.ok}
        >
          {children}
        </SiteShell>
      </body>
    </html>
  );
}
