SET TimeZone = 'UTC';

DELETE FROM mart_.bluesky_music_feed;

INSERT INTO mart_.bluesky_music_feed (
    week_start,
    uri,
    did,
    created_at,
    text,
    link_urls,
    hashtags,
    matched_rules,
    like_count,
    repost_count,
    reply_count
)
WITH latest_posts AS (
    SELECT
        uri,
        did,
        created_at,
        text,
        link_urls,
        hashtags,
        matched_rules
    FROM raw_.bluesky_posts
    QUALIFY row_number() OVER (
        PARTITION BY uri
        ORDER BY ingested_at DESC
    ) = 1
),
latest_engagement AS (
    SELECT
        uri,
        like_count,
        repost_count,
        reply_count
    FROM raw_.bluesky_engagement
    QUALIFY row_number() OVER (
        PARTITION BY uri
        ORDER BY fetched_at DESC
    ) = 1
)
SELECT
    CAST(date_trunc('week', post.created_at) AS DATE),
    post.uri,
    post.did,
    post.created_at,
    post.text,
    post.link_urls,
    post.hashtags,
    post.matched_rules,
    coalesce(engagement.like_count, 0),
    coalesce(engagement.repost_count, 0),
    coalesce(engagement.reply_count, 0)
FROM latest_posts AS post
LEFT JOIN latest_engagement AS engagement
    ON engagement.uri = post.uri
WHERE
    list_has_any(
        post.matched_rules,
        [
            'link:bandcamp.com',
            'link:soundcloud.com',
            'link:open.spotify.com',
            'link:music.apple.com',
            'link:last.fm',
            'hashtag:#nowplaying',
            'hashtag:#newmusic',
            'hashtag:#newrelease',
            'intent:on_repeat',
            'intent:new_album',
            'intent:new_ep',
            'intent:new_single',
            'intent:just_dropped'
        ]
    )
    OR (
        list_has_any(
            post.matched_rules,
            ['link:youtube.com', 'link:youtu.be']
        )
        AND regexp_matches(
            lower(post.text),
            '(^|[^a-z])(song|music|album|ep|track|band|artist|listen|listening|lyric|lyrics|chorus|record|playlist|earworm|sing|concert)([^a-z]|$)'
        )
    )
    OR (
        list_contains(post.matched_rules, 'hashtag:#np')
        AND (
            regexp_matches(lower(post.text), '#music([^a-z]|$)')
            OR regexp_matches(
                post.text,
                '^[^\n]{2,80} - [^\n]{2,80}'
            )
        )
    )
    OR (
        list_contains(post.matched_rules, 'intent:listening_to')
        AND regexp_matches(
            post.text,
            '[Ll]istening\s+to\s+(the\s+)?[A-Z0-9][A-Za-z0-9&.''’_-]*'
        )
    );
