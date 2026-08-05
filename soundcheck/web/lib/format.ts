import type { EstimateBand } from "@/lib/types";

const compact = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const dateFormat = new Intl.DateTimeFormat("en", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

export function formatNumber(value: number, digits = 2): string {
  return value.toLocaleString("en", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: value === 0 ? "never" : "exceptZero",
  });
}

export function formatPlain(value: number, digits = 2): string {
  return value.toLocaleString("en", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatCompact(value: number): string {
  return compact.format(value);
}

export function formatWeek(value: string): string {
  return dateFormat.format(new Date(`${value}T00:00:00Z`));
}

export function formatInterval(
  band: EstimateBand,
  digits = 2,
): string {
  return `${formatNumber(band.lower, digits)} — ${formatNumber(
    band.upper,
    digits,
  )}`;
}

export function genreSlug(genre: string): string {
  return encodeURIComponent(genre.toLowerCase().replaceAll(" ", "-"));
}

export function genreFromSlug(slug: string): string {
  return decodeURIComponent(slug).replaceAll("-", " ");
}

export function titleCase(value: string): string {
  return value.replace(/\b\w/g, (character) => character.toUpperCase());
}

export function modelLabel(value: string): string {
  const labels: Record<string, string> = {
    naive: "Naive",
    seasonal_naive: "Seasonal naive",
    ets: "ETS",
    lightgbm: "LightGBM",
  };
  return labels[value] ?? value;
}

export function blueskyUrl(uri: string, did: string): string {
  const recordKey = uri.split("/").at(-1);
  return `https://bsky.app/profile/${encodeURIComponent(
    did,
  )}/post/${encodeURIComponent(recordKey ?? "")}`;
}

export function lastfmUrl(artistName: string): string {
  return `https://www.last.fm/music/${encodeURIComponent(artistName)}`;
}

export function musicbrainzUrl(mbid: string): string {
  return `https://musicbrainz.org/release-group/${encodeURIComponent(
    mbid,
  )}`;
}

export function gapColor(value: number): string {
  if (value > 0.35) return "#8196d8";
  if (value < -0.35) return "#b98585";
  return "#7b7b83";
}

export function openingColor(value: number | null): string {
  if (value === null) return "#55555c";
  if (value > 0.4) return "#8196d8";
  if (value < -0.4) return "#a47777";
  return "#73737b";
}
