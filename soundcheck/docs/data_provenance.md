# Data Provenance

Soundcheck uses only official, documented, free APIs. Raw observations retain
their source identifiers and collection timestamps so every downstream number
can link back to its evidence.

## Bluesky

### What is collected

- Public `app.bsky.feed.post` commits from Jetstream that match the documented
  music-link, hashtag, or intent rules.
- Post AT URI, author DID, UTC creation time, text, languages, link facets,
  hashtags, matched rules, and UTC ingestion time.
- Public like, repost, and reply counts from AppView, appended at each poll
  time. Polls target approximately 24 and 72 hours after post creation and
  retain the target age and scheduled or overdue-recovery status.

### Rate limit and enforcement

Jetstream uses one long-lived public WebSocket filtered to feed-post commits.
AppView requests use the documented maximum of 25 post URIs per `getPosts`
request. Soundcheck does not rely on an unpublished numeric Bluesky request
limit; reconnects use exponential backoff. Each clean flush appends the latest
Jetstream microsecond cursor, and the next scheduled run requests replay from
the following cursor before reaching the live tail.

The daily workflow polls currently due targets and then runs the resumable
`make recover-bluesky-engagement` command. Recovery selects a deterministic
bounded batch and becomes restart-safe as soon as its append-only target poll
is stored. A 72-hour target, including a labeled overdue recovery, is required
for mature engagement. Until then, engagement counts remain missing rather
than becoming zeros.

### Authentication

None. Only public Jetstream and public AppView data are used.

### Deliberate exclusions

No private data, direct messages, authenticated feeds, follower graphs,
profiles, media downloads, or scraped pages are collected.

### Retention

Matched raw posts and engagement polls are append-only and retained with their
evidence identifiers in published DuckDB artifacts.

## Last.fm

### What is collected

- For every source spelling declared by an enabled or candidate taxonomy-v2
  genre in `config/genre_canonical.yml`, cumulative tag reach and total
  taggings, the top 100 artists, and the top 50 albums.
- For every artist observed in either top list, cumulative listeners and
  lifetime playcount, MusicBrainz ID when present, and public tags.
- Every observation carries a UTC `fetched_at` and is appended to
  `raw_.lastfm_tag_snapshots` or `raw_.lastfm_artist_snapshots`.

Last.fm totals are cumulative lifetime values, not listening events. Weekly
listening signals are calculated only as deltas between later snapshots. First
observations are excluded and are never interpreted or zero-filled as weekly
activity.

### Rate limit and enforcement

Soundcheck's operating limit is 4 requests per second. The async client evenly
spaces request starts at least 250 milliseconds apart, applies exponential
backoff to transient failures and Last.fm rate-limit errors, and caches
responses on disk under SHA-256 keys. Cache entries expire after six hours so
weekly cumulative snapshots cannot be frozen by stale cache data.

### Authentication

Read methods require `LASTFM_API_KEY`, supplied only through the environment.
No user session or account authentication is used. The key is never logged or
included in a cache key or cache payload.

### Deliberate exclusions

No usernames, user libraries, user playcounts, individual scrobbles, listening
histories, biographies, images, or private/account data are collected.

### Retention

Raw tag and artist snapshots are append-only and retained indefinitely in
published DuckDB artifacts so valid deltas can be reconstructed. The HTTP cache
is disposable and is not source-of-record storage.

The scheduled collector runs once per ISO week at the Monday 06:47 UTC workflow
trigger. Its checkpoint key is the UTC ISO year/week, so retries resume the
same observation and a second workflow invocation cannot manufacture another
historical snapshot. Manual and recovery runs retain their actual observation
time; Soundcheck never backdates a Last.fm snapshot.

### Automatic readiness promotion

The GitHub Actions workflow has one weekly collection run and six lightweight
daily recovery runs. Every run collects public Bluesky conversation, polls due
and overdue 24-hour and 72-hour engagement, completes the closed MusicBrainz
window, resolves the new evidence, and refreshes coverage. Only the Monday
06:47 UTC run collects Last.fm, preserving one stable snapshot boundary per
UTC ISO week.

After resolution, `soundcheck.scripts.plan_promotion` performs a read-only
maturity check. It prints source counts, maturity-state counts, the first and
latest eligible complete weeks, and whether either v1 or v2 has a complete
week newer than production. A daily run executes metrics, forecasts, briefs,
artifact publication, and deployment only when that condition is true. A
retry sees the same latest published week and skips the expensive downstream
chain, making promotion resumable and idempotent. Weekly runs still execute
the full chain so code, contracts, and statistical validation cannot drift.

This schedule removes the extra wait for the following Monday: once the last
posts in a closed week have a mature 72-hour poll, the next daily run promotes
the week automatically. It does not weaken the Last.fm 4-request-per-second
limit or MusicBrainz 1-request-per-second limit; those source limits define the
minimum safe collection time.

## MusicBrainz

### What is collected

- Release groups whose first-release date falls inside the requested window
  and whose public tags overlap source spellings declared by enabled or
  candidate taxonomy-v2 genres in `config/genre_canonical.yml`.
- Release-group MBID, title, structured artist credits and artist MBIDs,
  first-release date, primary and secondary types, genres, counted tags, and
  UTC fetch time.
- Incremental runs cover the trailing two fully closed ISO weeks, ending on
  the Sunday before the current ISO week. Backfill runs accept arbitrary
  closed ISO date ranges.

Release-group rows are insert-on-first-sight by MBID. Existing rows are never
updated because first-release dates are treated as stable supply facts. This
is intentionally asymmetric with cumulative Last.fm snapshots.

### Rate limit and enforcement

The official limit is strictly one request per second. The async client spaces
all uncached request starts at least one second apart, sends the required
`Soundcheck/0.1 ( contact-email )` User-Agent (with the deployment contact
loaded from `MUSICBRAINZ_CONTACT_EMAIL`), applies exponential backoff, and uses
a 24-hour SHA-256 disk cache. Search pages request at most 100 records.

Every completed query window is recorded only after all deterministic shards
and pages finish. Weekly supply accepts only parseable full `YYYY-MM-DD`
first-release dates. A fully covered closed Monday-through-Sunday window can
therefore support a true zero-release result; the open current week remains
`supply_pending` regardless of any partial release observations.

### Authentication

None. Soundcheck uses only unauthenticated public read endpoints.

### Deliberate exclusions

No editor or user data, private collections, submissions, recordings, edition
level releases, cover art, media files, or scraped MusicBrainz pages are
collected.

### Retention

The first observed release-group row is retained indefinitely in published
DuckDB artifacts. Later observations of the same MBID are ignored. The HTTP
cache is disposable.

## Rejected Sources

- **SoundCloud:** rejected because app registration requires the paid Artist
  Pro prerequisite.
- **Bandcamp:** rejected because there is no official API; using it would
  require scraping.

These sources remain rejected. Soundcheck does not scrape them.
