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
  time. Polls are designed for approximately 24 and 72 hours after ingestion.

### Rate limit and enforcement

Jetstream uses one long-lived public WebSocket filtered to feed-post commits.
AppView requests use the documented maximum of 25 post URIs per `getPosts`
request. Soundcheck does not rely on an unpublished numeric Bluesky request
limit; reconnects use exponential backoff. Each clean flush appends the latest
Jetstream microsecond cursor, and the next scheduled run requests replay from
the following cursor before reaching the live tail.

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

## MusicBrainz

### What is collected

- Release groups whose first-release date falls inside the requested window
  and whose public tags overlap source spellings declared by enabled or
  candidate taxonomy-v2 genres in `config/genre_canonical.yml`.
- Release-group MBID, title, structured artist credits and artist MBIDs,
  first-release date, primary and secondary types, genres, counted tags, and
  UTC fetch time.
- Incremental runs cover the inclusive trailing 14 days. Backfill runs accept
  arbitrary ISO date ranges.

Release-group rows are insert-on-first-sight by MBID. Existing rows are never
updated because first-release dates are treated as stable supply facts. This
is intentionally asymmetric with cumulative Last.fm snapshots.

### Rate limit and enforcement

The official limit is strictly one request per second. The async client spaces
all uncached request starts at least one second apart, sends the required
`Soundcheck/0.1 ( contact-email )` User-Agent (with the deployment contact
loaded from `MUSICBRAINZ_CONTACT_EMAIL`), applies exponential backoff, and uses
a 24-hour SHA-256 disk cache. Search pages request at most 100 records.

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
