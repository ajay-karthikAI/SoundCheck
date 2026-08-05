SELECT
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
FROM mart_.bluesky_music_feed
WHERE week_start = ?
ORDER BY
    CASE
        WHEN list_has_any(
            matched_rules,
            [
                'hashtag:#nowplaying',
                'hashtag:#newmusic',
                'hashtag:#newrelease',
                'intent:listening_to',
                'intent:on_repeat',
                'intent:new_album',
                'intent:new_ep',
                'intent:new_single',
                'intent:just_dropped'
            ]
        ) THEN 0
        WHEN list_has_any(
            matched_rules,
            [
                'link:bandcamp.com',
                'link:soundcloud.com',
                'link:open.spotify.com',
                'link:music.apple.com',
                'link:last.fm',
                'hashtag:#np'
            ]
        ) THEN 1
        ELSE 2
    END,
    created_at DESC,
    uri
LIMIT ?;
