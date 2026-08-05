export function previousIsoWeeks(
  latestWeek: string | null,
  count = 26,
): string[] {
  if (!latestWeek) return [];
  const latest = new Date(`${latestWeek}T00:00:00Z`);
  return Array.from({ length: count }, (_, index) => {
    const value = new Date(latest);
    value.setUTCDate(latest.getUTCDate() - index * 7);
    return value.toISOString().slice(0, 10);
  });
}
