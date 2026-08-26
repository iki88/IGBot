# InstaAddict Engine — Configuration Key Map

Complete, source-verified list of every configuration key the legacy InstaAddict engine registers and reads, across
its three per-account files: `config.yml`, `filters.yml`, and `telegram.yml`. Compiled directly from
`InstaAddict/plugins/core_arguments.py`, every plugin's `self.arguments` block, `InstaAddict/core/filter.py`, and
`InstaAddict/plugins/telegram.py` — not from IGBot's `igbot-*` keys, which are a separate, currently disconnected
vocabulary (see the architecture audit artifact for that gap).

Columns: **Section** (which YAML file), **Key**, **Type**, **Default**, **Module** (which automation concept it
drives), **Suggested UI Control** (given IGBot's existing `CollapsibleSection` / `CheckboxGroup` / `NumericSettings`
widget toolkit), **Notes**.

No source files were modified to produce this document.

---

## 1. Account Identity

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| config.yml | `username` | string | *(none — required)* | Account Identity | Text field | Already implemented in Overview tab |
| config.yml | `device` | string | *(none)* | Account Identity | Read-only field, populated from device assignment | ADB serial |
| config.yml | `app-id` | string | `"com.instagram.android"` | Account Identity | Text field + "Detect App ID" / "Load App IDs" buttons | Already implemented; legacy code also accepts `app_id` for backward compatibility |
| config.yml | `use-cloned-app` | bool | `false` | Account Identity | Toggle switch | Registered in `cloned_app.py`; no IGBot control yet |

---

## 2. Global / Core Behavior

Session-wide switches that apply regardless of which jobs are enabled.

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| config.yml | `speed-multiplier` | int (or float) | `1` | Global Settings | Numeric field | Slows (<1) or speeds up (>1) all random sleep values |
| config.yml | `debug` | bool | `false` | Global Settings | Toggle switch | Enables debug logging, skips countdown |
| config.yml | `screen-sleep` | bool | `false` | Global Settings | Toggle switch | Turns screen off during inactive time |
| config.yml | `screen-record` | bool | `false` | Global Settings | Toggle switch | Debug screen recording |
| config.yml | `close-apps` | bool | `false` | Global Settings | Toggle switch | Closes background apps except IG |
| config.yml | `kill-atx-agent` | bool | `false` | Global Settings | Toggle switch | Kills atx-agent when script ends |
| config.yml | `restart-atx-agent` | bool | `false` | Global Settings | Toggle switch | Restarts atx-agent before script starts |
| config.yml | `disable-block-detection` | bool | **`true`** | Global Settings | Toggle switch, label carefully | `action="store_false"` with no explicit default → block detection is **disabled by default**; setting this key to `false` in config.yml **enables** detection. Inverted semantics — word the UI label as "Enable block detection" bound to the negated value, not a literal passthrough |
| config.yml | `disable-filters` | bool | `false` | Global Settings | Toggle switch | Bypasses `filters.yml` entirely without renaming the file |
| config.yml | `dont-type` | bool | `false` | Global Settings | Toggle switch | Pastes text instead of typing (comments/PMs) |
| config.yml | `allow-untested-ig-version` | bool | `false` | Global Settings | Toggle switch | Skips the version-mismatch confirmation prompt |
| config.yml | `pre-script` | string (path) | `None` | Global Settings | File picker | Runs before each session |
| config.yml | `post-script` | string (path) | `None` | Global Settings | File picker | Runs after each session |
| config.yml | `move-folders-in-accounts` | bool | `false` | Global Settings | Toggle switch | One-time migration helper |
| config.yml | `uia-version` | int | `2` | Global Settings | *(omit from UI)* | Explicitly marked "deprecated" in its own help text |
| config.yml | `total-crashes-limit` | string (int or range) | `"5"` | Global Settings | Range input | Session-wide crash tolerance |
| config.yml | `count-app-crashes` | bool | `false` | Global Settings | Toggle switch | Whether an app crash/lost-view counts toward the crash limit |
| config.yml | `total-interactions-limit` | string (int or range) | `"1000"` | Global Settings | Range input | Overall per-session interaction cap, across all job types |
| config.yml | `total-successful-interactions-limit` | string (int or range) | `"100"` | Global Settings | Range input | Overall per-session *successful*-interaction cap |

---

## 3. Timer / Scheduling

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| config.yml | `working-hours` | list[string] | `["00.00-23.59"]` | Timer | Multi-window schedule editor (add/remove `HH.MM-HH.MM` rows) | Supports multiple non-contiguous windows in one session; current IGBot Timer tab only supports one start/end pair |
| config.yml | `time-delta` | string (int or range) | `"0"` | Timer | Range input | Offsets the working-hours check |
| config.yml | `repeat` | string (int or range) | `None` (disabled) | Timer | Range input, with an "enabled" toggle for the None state | Minutes to sleep before starting the next session |
| config.yml | `total-sessions` | int | `-1` (infinite) | Timer | Numeric field, with "-1 = infinite" affordance | Session-count cap |
| config.yml | `shuffle-jobs` | bool | `false` | Timer | Toggle switch | Randomizes job execution order each session |

---

## 4. Sources & Targeting

The lists that drive *what* an interaction job iterates over. These are shared inputs — the same "which profiles do
we visit" concept — that Follow/Like/Story/Comment/DM all ride on top of via `interaction.py`'s shared routine, so
they don't belong to any single action-type tab.

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| config.yml | `blogger` | list[string] | `None` | Sources | Text-list editor (one username per line) | *operation* — interact with a blogger's own posts |
| config.yml | `blogger-followers` | list[string] | `None` | Sources | Text-list editor | *operation* |
| config.yml | `blogger-following` | list[string] | `None` | Sources | Text-list editor | *operation* |
| config.yml | `blogger-post-likers` | list[string] | `None` | Sources | Text-list editor | *operation* |
| config.yml | `blogger-post-limits` | int | `0` | Sources | Numeric field | Caps how many of the blogger's posts are scanned for likers |
| config.yml | `hashtag-likers-top` | list[string] | `None` | Sources | Text-list editor (hashtags) | *operation* |
| config.yml | `hashtag-likers-recent` | list[string] | `None` | Sources | Text-list editor | *operation* |
| config.yml | `hashtag-posts-top` | list[string] | `None` | Sources | Text-list editor | *operation* |
| config.yml | `hashtag-posts-recent` | list[string] | `None` | Sources | Text-list editor | *operation* |
| config.yml | `place-likers-top` | list[string] | `None` | Sources | Text-list editor (place names) | *operation* |
| config.yml | `place-likers-recent` | list[string] | `None` | Sources | Text-list editor | *operation* |
| config.yml | `place-posts-top` | list[string] | `None` | Sources | Text-list editor | *operation* |
| config.yml | `place-posts-recent` | list[string] | `None` | Sources | Text-list editor | *operation* |
| config.yml | `interact-from-file` | list[string] | `None` | Sources | File-list editor with a per-file count range (e.g. `usernames1.txt 10-15`) | *operation* — target list read from a `.txt` file |
| config.yml | `unfollow-from-file` | list[string] | `None` | Unfollow | File-list editor, same format as above | *operation*, registered in `interact_blogger.py` despite the name |
| config.yml | `posts-from-file` | list[string] | `None` | Like | File-list editor (post-URL files) | *operation* — `LikeFromURLs` plugin, likes posts by URL, not a source of *profiles* |
| config.yml | `feed` | string (int or range) | `None` | Sources | Range input | *operation* — interacts with other users' posts in your own feed. **Not post creation** |
| config.yml | `remove-followers-from-file` | list[string] | `None` | Unfollow | File-list editor | *operation* — bulk-removes followers listed in a file |
| config.yml | `interact-percentage` | string (int or range) | `"50"` | Sources | Range input | Chance to engage a hashtag/place post owner |
| config.yml | `interactions-count` | string (int or range) | `"30-50"` | Sources | Range input | Successful-interaction cap per blogger |
| config.yml | `skipped-list-limit` | string (int or range) | `"10-15"` | Sources | Range input | Scroll-until-give-up threshold before moving to next source |
| config.yml | `skipped-posts-limit` | string (int or range) | `"5"` | Sources | Range input | Post-skip threshold before moving to next source |
| config.yml | `fling-when-skipped` | string (int or range) | `"0"` | Sources | Range input | Fling instead of scroll after N skips (not recommended) |
| config.yml | `can-reinteract-after` | string (int or range) | `None` | Sources | Range input, with an "enabled" toggle | Hours before re-interacting with the same user |
| config.yml | `truncate-sources` | string (int or range) | `"0"` | Sources | Range input | Trims the source list to a finite number of items |
| config.yml | `scrape-to-file` | string (filename) | `None` | Sources | Text field, with an "enabled" toggle | Scrape-mode instead of interacting; writes targets to a file |
| config.yml | `total-scraped-limit` | string (int or range) | `"50"` | Sources | Range input | Cap on scraped users per session |
| config.yml | `delete-interacted-users` | bool | `false` | Sources | Toggle switch | Deletes a username from its source file after processing |

---

## 5. Follow

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| config.yml | `follow-percentage` | string (int or range) | `"0"` | Follow | Range input | Chance to follow an interacted user |
| config.yml | `follow-limit` | string (int or range) | `None` (disabled) | Follow | Range input, with an "enabled" toggle | Per-source follow cap |
| config.yml | `total-follows-limit` | string (int or range) | `"50"` | Follow | Range input | Per-session follow cap |
| config.yml | `end-if-follows-limit-reached` | bool | `false` | Follow | Toggle switch | Ends the session once the follow limit is hit |
| filters.yml | `follow_private_or_empty` | bool | `false` | Follow | Toggle switch | Whether to follow private/empty-bio accounts |

---

## 6. Unfollow

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| config.yml | `unfollow` | string (int or range) | `None` | Unfollow | Range input under a mode selector | *operation* — unfollow bot-followed users, oldest→newest |
| config.yml | `unfollow-non-followers` | string (int or range) | `None` | Unfollow | Range input under a mode selector | *operation* — bot-followed users who don't follow back |
| config.yml | `unfollow-any-non-followers` | string (int or range) | `None` | Unfollow | Range input under a mode selector | *operation* — anyone who doesn't follow back |
| config.yml | `unfollow-any-followers` | string (int or range) | `None` | Unfollow | Range input under a mode selector | *operation* — anyone who does follow back |
| config.yml | `unfollow-any` | string (int or range) | `None` | Unfollow | Range input under a mode selector | *operation* — anyone, regardless of origin |
| config.yml | `min-following` | int | `0` | Unfollow | Numeric field | Floor — stop unfollowing once following count reaches this |
| config.yml | `sort-followers-newest-to-oldest` | bool | `false` | Unfollow | Toggle switch | Default iteration order is oldest→newest |
| config.yml | `unfollow-delay` | string (int days) | `"0"` | Unfollow | Numeric field (days) | Days since follow before an account becomes eligible for unfollow |
| config.yml | `total-unfollows-limit` | string (int or range) | `"50"` | Unfollow | Range input | Per-session unfollow cap |
| config.yml | `delete-removed-followers` | bool | `false` | Unfollow | Toggle switch | Deletes a username from `remove-followers-from-file` after removal |

*(`unfollow-from-file` and `remove-followers-from-file` are listed under §4 — they're file-based target lists, not counts.)*

---

## 7. Like

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| config.yml | `likes-count` | string (int or range) | `"1-2"` | Like | Range input | Likes per profile's photo grid |
| config.yml | `likes-percentage` | string (int or range) | `"100"` | Like | Range input | Chance of liking at all on a given profile |
| config.yml | `total-likes-limit` | string (int or range) | `"300"` | Like | Range input | Per-session like cap |
| config.yml | `end-if-likes-limit-reached` | bool | `false` | Like | Toggle switch | Ends the session once the like limit is hit |
| config.yml | `carousel-count` | string (int or range) | `"1"` | Like | Range input | Carousel photos browsed |
| config.yml | `carousel-percentage` | string (int or range) | `"60-70"` | Like | Range input | Chance of browsing a carousel post |
| config.yml | `watch-photo-time` | string (int or range, seconds) | `"3-4"` | Like | Range input (seconds) | Dwell time on a photo before liking; `0` disables |
| config.yml | `watch-video-time` | string (int or range, seconds) | `"15-30"` | Like | Range input (seconds) | Dwell time on a video/Reel before liking; `0` disables. Also the only key Reels currently uses |
| filters.yml | `min_likers` | int | `1` | Like | Numeric field | Minimum likers for a "likers"-sourced job to consider a post |
| filters.yml | `max_likers` | int | `1000` | Like | Numeric field | Maximum likers for the same filter |

---

## 8. Story

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| config.yml | `stories-count` | string (int or range) | `"0"` | Story | Range input | Stories watched per profile |
| config.yml | `stories-percentage` | string (int or range) | `"30-40"` | Story | Range input | Chance of watching stories on a given profile |
| config.yml | `total-watches-limit` | string (int or range) | `"50"` | Story | Range input | Per-session story-watch cap |
| config.yml | `end-if-watches-limit-reached` | bool | `false` | Story | Toggle switch | Ends the session once the watch limit is hit |

No separate "auto-like story" key exists — `_watch_stories()` likes the story automatically while watching; there is
nothing to expose as an independent toggle.

---

## 9. Comment

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| config.yml | `comment-percentage` | string (int or range) | `"0"` | Comment | Range input | Chance of commenting on an interacted user |
| config.yml | `total-comments-limit` | string (int or range) | `"0"` (disabled) | Comment | Range input | Per-session comment cap |
| config.yml | `max-comments-pro-user` | string (int or range) | `"1"` | Comment | Range input | Max comments per individual user |
| config.yml | `end-if-comments-limit-reached` | bool | `false` | Comment | Toggle switch | Ends the session once the comment limit is hit |
| filters.yml | `comment_photos` | bool | `true` | Comment | Toggle switch | Enables commenting on photo posts |
| filters.yml | `comment_videos` | bool | `true` | Comment | Toggle switch | Enables commenting on video posts |
| filters.yml | `comment_carousels` | bool | `true` | Comment | Toggle switch | Enables commenting on carousel posts |
| filters.yml | `comment_hashtag_likers_top` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_hashtag_likers_recent` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_hashtag_posts_top` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_hashtag_posts_recent` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_place_likers_top` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_place_likers_recent` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_place_posts_top` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_place_posts_recent` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_blogger_followers` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_blogger_following` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_blogger_post_likers` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_blogger` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_interact_usernames` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_interact_from_file` | bool | `true` | Comment | Toggle switch (per-source matrix) | |
| filters.yml | `comment_feed` | bool | `false` | Comment | Toggle switch (per-source matrix) | |
| — | `comments_list.txt` | file (spintax text) | *(template file)* | Comment | Text-bank editor, sectioned by `%PHOTO` / `%VIDEO` / `%CAROUSEL` | Not a `config.yml`/`filters.yml` key — a plaintext bank in `accounts/<user>/comments_list.txt`, supports spintax and emoji |

---

## 10. DM

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| config.yml | `pm-percentage` | string (int or range) | `"0"` | DM | Range input | Chance of sending a PM to an interacted user |
| config.yml | `total-pm-limit` | string (int or range) | `"0"` (disabled) | DM | Range input | Per-session PM cap |
| config.yml | `end-if-pm-limit-reached` | bool | `false` | DM | Toggle switch | Ends the session once the PM limit is hit |
| filters.yml | `pm_to_private_or_empty` | bool | `true` | DM | Toggle switch | Whether to PM private/empty-bio accounts |
| — | `pm_list.txt` | file (spintax text) | *(template file)* | DM | Text-bank editor | Not a `config.yml`/`filters.yml` key — plaintext bank in `accounts/<user>/pm_list.txt`, spintax + emoji support |

---

## 11. Reporting & Post-Processing

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| config.yml | `telegram-reports` | bool | `false` | Reporting | Toggle switch | *operation* — sends an end-of-session summary via Telegram; requires `telegram.yml` |
| telegram.yml | `telegram-api-token` | string | *(placeholder)* | Reporting | Text field (masked, like a password) | From `@BotFather` |
| telegram.yml | `telegram-chat-id` | string | *(placeholder)* | Reporting | Text field | From `@myidbot` |
| config.yml | `analytics` | bool | `false` | Reporting | *(omit from UI)* | Registered `operation`, but the plugin body is a stub — matplotlib was removed and the feature is broken; do not surface as a working option |

---

## 12. Filters — Profile, Stats & Language

All from `filters.yml`, consumed by `InstaAddict/core/filter.py::check_profile()`. These gate Follow/Like/Comment/DM
uniformly — they aren't specific to one action-type tab, so they'd naturally live in a shared "Filters" section (the
Overview tab's reserved "Filters" card is the obvious home).

| Section | Key | Type | Default | Module | Suggested UI Control | Notes |
|---|---|---|---|---|---|---|
| filters.yml | `skip_if_private` | bool | `false` | Filters | Toggle switch | |
| filters.yml | `skip_if_public` | bool | `false` | Filters | Toggle switch | |
| filters.yml | `skip_business` | bool | `true` | Filters | Toggle switch | |
| filters.yml | `skip_non_business` | bool | `false` | Filters | Toggle switch | |
| filters.yml | `skip_following` | bool | `true` | Filters | Toggle switch | Skip accounts you already follow |
| filters.yml | `skip_follower` | bool | `true` | Filters | Toggle switch | Skip accounts that already follow you |
| filters.yml | `skip_if_link_in_bio` | bool | `true` | Filters | Toggle switch | |
| filters.yml | `min_followers` | int | `50` | Filters | Numeric field | |
| filters.yml | `max_followers` | int | `2500` | Filters | Numeric field | |
| filters.yml | `min_followings` | int | `50` | Filters | Numeric field | |
| filters.yml | `max_followings` | int | `2500` | Filters | Numeric field | |
| filters.yml | `min_potency_ratio` | float | `0.5` | Filters | Numeric field (decimal) | followers ÷ following ratio |
| filters.yml | `max_potency_ratio` | float | `5` | Filters | Numeric field (decimal) | |
| filters.yml | `min_posts` | int | `3` | Filters | Numeric field | |
| filters.yml | `mutual_friends` | int | `-1` (ignored) | Filters | Numeric field, with a "-1 = ignore" affordance | |
| filters.yml | `blacklist_words` | list[string] | `[sex, link]` | Filters | Text-list editor (bio keyword blocklist) | |
| filters.yml | `mandatory_words` | list[string] | `[cat, dogs]` | Filters | Text-list editor (bio keyword allowlist) | |
| filters.yml | `specific_alphabet` | list[string] | `[LATIN, GREEK]` | Filters | Multi-select | |
| filters.yml | `biography_language` | list[string] | `[it, en]` | Filters | Text-list editor (language codes) | |
| filters.yml | `biography_banned_language` | list[string] | `[es, ch]` | Filters | Text-list editor (language codes) | |

---

## 13. Legacy / Deprecated Keys

Still registered (so they won't trigger the "unknown arguments" abort), but explicitly non-functional or superseded.
**None of these should get a new UI control.**

| Section | Key | Type | Default | Status | Notes |
|---|---|---|---|---|---|
| config.yml | `interact` | list[string] | `None` | Accepted, ignored at runtime | `_is_legacy_arg()` in `config.py` logs a warning and excludes it from `enabled` jobs even if present |
| config.yml | `hashtag-likers` | list[string] | `None` | Accepted, ignored at runtime | Same `_is_legacy_arg()` path as `interact` |
| config.yml | `uia-version` | int | `2` | Accepted, marked deprecated in its own help text | No longer meaningful |
| — | `detect-block` | bool | — | **Rejected**, not registered at all | Not a real key — if present, it lands in `unknown_args` and `Config.parse_args()` prints a specific message redirecting to `disable-block-detection` |
| — | `filter.json` | file | — | Deprecated since v2.3.0 | `Storage`/`Filter` still fall back to it only when `filters.yml` is absent |

---

## Summary

- **93** keys registered in `config.yml` (via `core_arguments.py` + all plugin `self.arguments` blocks)
- **40** keys in `filters.yml`
- **2** keys in `telegram.yml`
- **2** free-text bank files (`comments_list.txt`, `pm_list.txt`) that function as configuration but aren't YAML keys
- **3** effectively dead/rejected keys (`interact`, `hashtag-likers`, `detect-block`)

None of the `igbot-follow-*` / `igbot-timer-*` keys IGBot's Follow and Timer tabs currently write appear anywhere in
this document — they are a separate vocabulary the engine does not read. See the architecture audit for that gap and
the recommended remediation.
