# InstaAddict Follow Engine Audit

## Scope and Method

This document audits the Follow capability that currently exists in the bundled
`InstaAddict` engine. It is based on the registered engine arguments, the example
configuration, the source plugins, the shared interaction pipeline, filtering,
session state, and per-account storage. It does not describe planned IGBot features
unless the current engine already implements them.

Primary implementation areas reviewed:

- `InstaAddict/plugins/core_arguments.py`
- `InstaAddict/plugins/interact_*.py`
- `InstaAddict/core/bot_flow.py`
- `InstaAddict/core/handle_sources.py`
- `InstaAddict/core/interaction.py`
- `InstaAddict/core/filter.py`
- `InstaAddict/core/storage.py`
- `InstaAddict/core/session_state.py`
- `InstaAddict/core/navigation.py`
- `InstaAddict/core/config.py`
- `config-examples/config.yml`
- `config-examples/filters.yml`
- `ENGINE_CONFIG_MAP.md`

## Executive Summary

InstaAddict does not implement Follow as a collection of independent “Follow
methods.” It implements a collection of **interaction source jobs**. Every active
source job eventually calls the same `interact_with_user()` routine, where Story,
Like, Comment, DM, and Follow may all occur. Follow is enabled globally by a
non-zero `follow-percentage`; it is not enabled separately for each source.

The engine currently has 13 non-legacy source jobs capable of reaching the shared
Follow action, plus feed and a file-backed username source. The engine has four
direct Follow controls in `config.yml` and one Follow-specific filter in
`filters.yml`. All other profile filters and source controls are shared across the
interaction actions.

Key findings:

- `Follow User's Followers` and `Follow User's Followings` are real engine jobs.
- Direct interaction with specified users is supported through `blogger` and
  `interact-from-file`, but those two modes have different semantics.
- Hashtag and place targeting are supported through separate Top/Recent and
  Post/Liker jobs.
- There is no general keyword-search Follow job.
- `blogger-post-limits` is registered and documented but is not read by runtime
  code; it currently has no effect.
- `interact` and `hashtag-likers` are accepted legacy arguments but are deliberately
  excluded from execution.
- “Visit profile,” “scroll profile,” “like before/after follow,” and “mute” are not
  configurable Follow options. Visiting a profile is intrinsic to the pipeline;
  scrolling is an internal UI-navigation detail; Like is a separate shared action;
  Mute is not implemented.
- Filtering is performed once at the shared profile-interaction boundary and
  therefore affects Follow, Like, Comment, Story, and DM together.

## 1. Follow Methods and Interaction Sources

### Capability Matrix

All entries below are `config.yml` keys. None has a corresponding `filters.yml`
key merely to enable the source. Filters are applied later by the shared profile
filter.

| Operator concept | Engine key | Input | Runtime implementation | Status | Limitations |
|---|---|---|---|---|---|
| Follow a user's followers | `blogger-followers` | List of usernames | `plugins/interact_blogger_followers.py` navigates to each blogger and `core/handle_sources.py::handle_followers()` iterates the Followers list | Used | Instagram may restrict a user's list. The engine detects a restricted/empty result and skips that source. |
| Follow a user's followings | `blogger-following` | List of usernames | Same plugin and list iterator, selecting the Following list | Used | Same restricted-list and UI-scrolling limitations as Followers. |
| Follow users who liked a blogger's posts | `blogger-post-likers` | List of blogger usernames | `plugins/interact_blogger_post_likers.py`; opens blogger posts and iterates each post's liker list through `handle_likers()` | Used | Depends on liker lists being accessible. `blogger-post-limits` is not actually enforced. |
| Interact with specific users directly | `blogger` | List of usernames | `plugins/interact_blogger.py`; navigates directly to each profile and passes it to the common interaction routine | Used | Despite the historical name, this is the direct in-config username mode. Each listed profile is itself the interaction target. |
| Interact with usernames from files | `interact-from-file` | List entries such as `usernames.txt 10-15` | `plugins/interact_blogger.py` and `handle_blogger_from_file()` | Used | File must be inside the account directory. A per-file amount is sampled; default is 10 when omitted. |
| Follow likers of Top hashtag posts | `hashtag-likers-top` | List of hashtags | `plugins/interact_hashtag_likers.py` plus `handle_likers()` | Used | Relies on Instagram search and accessible liker lists. |
| Follow likers of Recent hashtag posts | `hashtag-likers-recent` | List of hashtags | Same plugin, Recent mode | Used | Same limitation; Recent availability is controlled by the current Instagram UI. |
| Follow owners of Top hashtag posts | `hashtag-posts-top` | List of hashtags | `plugins/interact_hashtag_posts.py` plus `handle_posts()` | Used | The source-post interaction is probabilistic through `interact-percentage`. |
| Follow owners of Recent hashtag posts | `hashtag-posts-recent` | List of hashtags | Same plugin, Recent mode | Used | Same limitation. |
| Follow likers of Top place posts | `place-likers-top` | List of place search terms | `plugins/interact_place_likers.py` plus `handle_likers()` | Used | Depends on Instagram place search and accessible liker lists. |
| Follow likers of Recent place posts | `place-likers-recent` | List of places | Same plugin, Recent mode | Used | Same limitation. |
| Follow owners of Top place posts | `place-posts-top` | List of places | `plugins/interact_place_posts.py` plus `handle_posts()` | Used | Source-post selection is also subject to `interact-percentage`. |
| Follow owners of Recent place posts | `place-posts-recent` | List of places | Same plugin, Recent mode | Used | Same limitation. |
| Follow owners reached from the home feed | `feed` | Integer or range indicating feed interactions | `plugins/interact_feed.py` plus `handle_posts()` | Used | Operates on the signed-in account's feed; it is not a deterministic audience list. |

### Related Source Keys

| Key | Default | Runtime state | Notes |
|---|---:|---|---|
| `blogger-post-limits` | `0` | Ineffective | Registered by `interact_blogger_post_likers.py`, but no runtime read exists. It presently does not cap scanned posts. |
| `interact-percentage` | `"50"` | Used | Chance of engaging a candidate from hashtag/place post-owner jobs. It gates reaching the profile interaction; it is not the Follow probability. |
| `interactions-count` | `"30-50"` | Used | Maximum successful interactions for each source. The source advances when this count is reached. |
| `truncate-sources` | `"0"` | Used | Samples/truncates the configured source list before execution. Zero leaves it unrestricted. |
| `can-reinteract-after` | `None` | Used | Hours before an entry in `interacted_users.json` is eligible again. `None` prevents reinteraction; `0` permits it immediately. |
| `skipped-list-limit` | `"10-15"` | Used | Stops list traversal after repeated pages of already-processed users. |
| `skipped-posts-limit` | `"5"` | Used | Advances after consecutive already-interacted posts in post-based jobs. |
| `fling-when-skipped` | `"0"` | Used | Changes list navigation from a normal scroll to a fling after repeated fully skipped pages. The engine help explicitly calls it not recommended. |

### Unsupported or Legacy “Methods”

| Concept/key | Finding |
|---|---|
| Keyword Search | No general username-keyword Follow source is registered or implemented. Hashtag and place search exist, but they must not be relabeled as generic keyword search. |
| `interact` | Registered for compatibility, but `Config._is_legacy_arg()` identifies it as legacy and excludes it from enabled jobs. Obsolete. |
| `hashtag-likers` | Registered for compatibility, but handled by the same legacy exclusion. The Top/Recent variants replace it. Obsolete. |
| Follow followers of own followers | No distinct key or plugin. It can only be approximated manually by supplying usernames to an existing source, so it is not an engine capability. |

## 2. Operational Follow Settings

### Follow-Specific Settings

| File | Engine key | Engine default | Description | Runtime usage |
|---|---|---:|---|---|
| `config.yml` | `follow-percentage` | `"0"` | Probability, from 0–100, that an eligible interacted profile will be followed. Accepts a value or range. | `init_on_things()` samples it for a source; `_follow()` makes a second random decision and skips when the sampled chance is exceeded. Zero disables Follow without disabling the source job. |
| `config.yml` | `follow-limit` | `None` | Per-source cap on successful follows. Accepts a value or range. | Every source plugin samples the configured limit and compares it with `SessionState.totalFollowed[source]`. Once reached, further candidates can still be processed for other actions, but `can_follow` becomes false. |
| `config.yml` | `total-follows-limit` | `"50"` | Total successful Follow cap for the session. Accepts a value or range. | Sampled at session start into `current_follow_limit`. `_follow()` refuses further follows at the cap. |
| `config.yml` | `end-if-follows-limit-reached` | `false` | Whether hitting the total Follow limit ends active-job processing. | Checked after interactions and by the outer session loop. If false, other actions and sources can continue while Follow remains capped. |
| `filters.yml` | `follow_private_or_empty` | no intrinsic filter default; example is `false` | Permits Follow on private profiles or profiles with zero posts. | `interact_with_user()` uses a special early branch. With the setting true, the engine can Follow without Story/Like/Comment processing; with it absent or false, such profiles are skipped (PM may still occur under its own filter). |

### Shared Controls That Affect Follow Throughput

These are operationally important to Follow but are not Follow-only settings.

| Engine key | Default | Effect on Follow |
|---|---:|---|
| `interactions-count` | `"30-50"` | Caps successful interactions per source and can advance the job before the Follow cap is reached. |
| `total-interactions-limit` | `"1000"` | Ends the session after the total candidate interaction count reaches the sampled cap. |
| `total-successful-interactions-limit` | `"100"` | Ends the session after successful combined interactions reach the cap. A Story, Like, Comment, DM, or Follow can make an interaction successful. |
| `working-hours` | `["00.00-23.59"]` | The engine checks working hours before and during source processing. Leaving the window stops the current session/job flow. |
| `time-delta` | `"0"` | Applies a randomized offset to the working-hours boundary. |
| `shuffle-jobs` | `false` | Changes which active source job executes first. |
| `speed-multiplier` | `1` | Alters shared randomized sleeps and therefore interaction pace; it is not a dedicated Follow delay. |

### Settings the Engine Does Not Have

There is no dedicated minimum/maximum delay after following, daily Follow limit,
Auto Increment, Increment Amount, Maximum Warmup Limit, warmup-day state, or
per-day Follow counter in the audited engine. The existing limits are per engine
session, not calendar-day limits. Such controls must not be persisted under invented
engine keys.

## 3. Additional Follow Behaviour

| Behaviour | Engine key | Actual runtime behaviour |
|---|---|---|
| Visit target profile | None | Mandatory and intrinsic. Source handlers navigate to the profile before `Filter.check_profile()` and `_follow()` can run. It is not optional. |
| Scroll profile before following | None | Not a user setting. If Likes are enabled and enough posts exist, `swipe_to_fit_posts()` may reposition the profile grid. `_follow()` may compensate with the returned swipe amount before finding the Follow button. |
| Like random posts before following | `likes-count`, `likes-percentage` | Like is an independent shared action, not a Follow behaviour flag. When enabled, visible post indices are shuffled, posts are opened/liked, then DM runs, then Follow runs. |
| Watch stories before following | `stories-count`, `stories-percentage` | Independent shared Story action. It runs before Likes and Follow for public, non-empty profiles. |
| Comment before following | `comment-percentage` plus comment filters/resources | Comments can occur while processing liked posts. This is independent of Follow. |
| Send DM before following | `pm-percentage` | DM runs after Story/Like/Comment and before Follow on normal profiles. Private/empty profiles use a special PM path. |
| Follow private or empty profiles | `follow_private_or_empty` in `filters.yml` | Supported by a dedicated early branch, as described above. |
| Avoid duplicate follows | No direct key | `interacted_users.json`, current Follow-button state, and `skip_following` cooperate. `_follow()` also refuses when the UI says Following/Requested or Follow Back. |
| Follow Back | None | `_follow()` deliberately does **not** follow when the button says Follow Back; it logs that the user already follows the operator and returns false. |
| Mute after follow | None | No implementation or registered key was found. |
| Retry Follow click | None | Internal fixed behavior: up to three click attempts, followed by Follow/Following state verification and block detection. Not configurable. |

### Actual Per-Profile Action Order

For a public profile with posts, the shared order is:

1. Read and filter the profile.
2. Watch Stories, if selected by percentage and within the Story limit.
3. Select, open, watch, and Like profile posts, if selected by percentage.
4. Comment while processing those posts, when eligible.
5. Send a DM, when selected and within limits.
6. Follow the profile, when the source and session Follow limits allow it and the
   Follow probability succeeds.
7. Persist interaction history and update session counters.

Therefore “Like after Follow” is not the current behavior: Like occurs before Follow.

## 4. Filters

All profile filters below are read from `filters.yml` by
`core/filter.py::Filter.check_profile()`. Unless noted, a missing key leaves that
filter inactive or unbounded. The values shown as examples are from
`config-examples/filters.yml`, not hard engine defaults.

### Relationship and Profile-Type Filters

| Key | Example | Runtime behavior |
|---|---:|---|
| `skip_following` | `true` | Skips when the profile button indicates the operator already follows the target. |
| `skip_follower` | `true` | Skips when the target already follows the operator (`Follow Back`). |
| `skip_if_private` | `false` | Skips private profiles. |
| `skip_if_public` | `false` | Defective as implemented: the condition tests `profile_data.is_private`, so enabling it skips private profiles while logging that the profile is public. Public profiles are not skipped by this branch. |
| `skip_business` | `true` | Skips profiles with a detected business category. |
| `skip_non_business` | `false` | Skips profiles without a business category. |
| `skip_if_link_in_bio` | `true` | Skips when a link is present in the biography. |
| `follow_private_or_empty` | `false` | Follow-specific exception allowing private or zero-post profiles through the special Follow branch. |

The engine always skips restricted profiles, incompletely loaded profiles, and
profiles whose privacy status cannot be determined. These checks are not optional.

### Numeric Profile Filters

| Key | Example | Runtime behavior |
|---|---:|---|
| `min_followers` | `50` | Skips profiles below the follower count. |
| `max_followers` | `2500` | Skips profiles above the follower count. |
| `min_followings` | `50` | Skips profiles below the following count. |
| `max_followings` | `2500` | Skips profiles above the following count. |
| `min_potency_ratio` | `0.5` | Lower bound for followers divided by followings; zero disables the lower bound. |
| `max_potency_ratio` | `5` | Upper bound for the same ratio; runtime fallback is 999. |
| `min_posts` | `3` | Skips profiles with fewer posts. There is no `max_posts` filter. |
| `mutual_friends` | `-1` | Requires at least the configured mutual-friend count; `-1` disables the check. |

### Biography, Name, Alphabet, and Language Filters

| Key | Example | Runtime behavior |
|---|---|---|
| `blacklist_words` | `[sex, link]` | Case-insensitive whole-word matching against a normalized biography; any match skips the profile. This is distinct from `blacklist.txt`. |
| `mandatory_words` | `[cat, dogs]` | At least one configured whole word must appear in the biography. |
| `specific_alphabet` | `[LATIN, GREEK]` | Requires the detected primary Unicode alphabet of both biography and full name to be allowed. Mathematical character sets are ignored by detection. |
| `biography_language` | `[it, en]` | Requires detected biography language to be in the allow-list. |
| `biography_banned_language` | `[es, ch]` | Skips when the detected biography language is in the deny-list. |

An empty biography is skipped when mandatory words, biography language, or a
specific alphabet must be checked. Language detection is performed by `langdetect`
and can be uncertain for short text.

### Source-Post Filters

| Key | Example | Runtime behavior |
|---|---:|---|
| `min_likers` | `1` | Lower bound for a source post's liker count before a liker-based source is processed. |
| `max_likers` | `1000` | Upper bound. The implementation uses Python's half-open `range(min, max)`, so the configured maximum is excluded rather than included. |

### External Lists and Interaction History

| Mechanism | Runtime behavior |
|---|---|
| `blacklist.txt` | Exact, case-sensitive username membership check before profile navigation/interaction. Blacklisted candidates are skipped. |
| `whitelist.txt` | Loaded by `Storage`; primarily protects users in Unfollow behavior. It is not used as a Follow allow-list. |
| `interacted_users.json` | Prevents repeated interaction unless `can-reinteract-after` permits it. Also records whether the account was followed/requested, source job, target, and action counts. |
| `history_filters_users.json` | Records fetched profile data and the filter skip reason for audit/history. It does not itself decide eligibility. |

There are no separate filters for username text, display-name words, gender, age,
country, or a dedicated Follow language setting. Biography/name alphabet and
biography language are the implemented equivalents and should be labeled precisely.

## 5. Follow-Related Resource Files

### Fixed Per-Account Files

| File | Purpose and format | Loaded by | Runtime usage |
|---|---|---|---|
| `config.yml` | YAML engine arguments and source lists | `core/config.py` | Selects active source jobs and all Follow/session controls. |
| `filters.yml` | YAML filter mapping | `core/storage.py` and `core/filter.py` | Gates candidate profiles and source posts. |
| `filter.json` | Legacy JSON equivalent | `core/storage.py` and `core/filter.py` | Used only when `filters.yml` is absent; explicitly deprecated. |
| `blacklist.txt` | One username per line | `core/storage.py` | Skips exact usernames before interaction. |
| `whitelist.txt` | One username per line | `core/storage.py` | Loaded as protected users, principally for Unfollow. |
| `interacted_users.json` | Engine-generated JSON object keyed by username | `core/storage.py` | Deduplication, reinteraction timing, following status, source and action history. |
| `history_filters_users.json` | Engine-generated JSON object keyed by username | `core/storage.py` | Stores profile snapshots and filter outcomes. |
| `sessions.json` | Engine-generated session history | `core/bot_flow.py` / `PersistentList` | Persists session counters and reports, including Follow totals. |

### Operator-Supplied Source Files

`interact-from-file` does not require a hardcoded `bloggers.txt`. Each configured
entry names a text file relative to `accounts/<account>/`, optionally followed by a
count or range:

```yaml
interact-from-file: [usernames1.txt 10-15, usernames2.txt 3]
```

Each file contains one username per line. Spaces are removed from entries. The
engine processes the sampled number of users. Missing profiles are appended to a
sibling `<source>_not_found.txt` file. When `delete-interacted-users: true`, the
processed prefix is removed from the source file using an atomic rewrite.

`comments_list.txt` and `pm_list.txt` may be consumed during the same shared
interaction, but they configure Comment and DM rather than Follow.

## 6. Runtime Flow

### Session and Job Pipeline

```text
InstaAddict start_bot()
  -> load plugins and parse config.yml
  -> create device and session state
  -> enforce working hours and initialize sampled session limits
  -> open Instagram and select the configured Instagram account
  -> create Storage and load filters.yml / lists / interaction history
  -> order enabled source jobs (configured order or shuffle-jobs)
  -> run each source plugin until its source, interaction, or session limit ends
  -> persist session history and close Instagram
```

The IGBot Phone Scheduler sits outside this legacy pipeline and selects which
account runtime to start. Once InstaAddict starts for an account, the sequence above
is the engine's actual internal scheduler/job flow.

### Source-to-Follow Pipeline

```text
Source plugin
  -> sample/truncate configured sources
  -> navigate to blogger, list, hashtag, place, file target, or feed
  -> enumerate candidate username
  -> blacklist and interacted-user pre-check
  -> open candidate profile
  -> read profile data
  -> apply shared filters
  -> private/empty special path, or normal action path
       -> Story
       -> Like and optional Comment
       -> DM
       -> Follow
  -> verify Follow button changed to Following/Requested
  -> detect action block
  -> persist interacted_users.json
  -> update per-source and session counters
  -> decide whether to continue current source/job
```

### Follow Eligibility and Execution Details

1. A source plugin computes a sampled `follow-limit` for that source.
2. `handle_sources.interact()` permits Follow only when the per-source limit is not
   reached and stored following status is `NONE` or `NOT_IN_LIST`.
3. The shared profile filter may reject the candidate before any action.
4. `_follow()` checks the total session Follow limit.
5. `_follow()` samples the configured `follow-percentage` outcome.
6. It locates Follow, Following/Requested, and Follow Back controls.
7. Follow Back and already-following states are deliberately skipped.
8. The Follow control is clicked up to three times and verified by the appearance of
   Following/Requested.
9. Block detection runs after success and after exhausted retries.
10. A successful Follow increments both the source Follow count and total session
    Follow count.

### Stop Conditions

Follow can stop for several independent reasons:

- `follow-limit` reached for the current source;
- `total-follows-limit` reached for the session;
- `end-if-follows-limit-reached` ending active-job execution;
- source `interactions-count` reached;
- total or successful interaction limits reached;
- working-hours window ended;
- source traversal exhausted or its skipped-list/skipped-post threshold was reached;
- navigation, restricted list, inaccessible profile, filtering, action block, or
  crash handling prevented progress.

## 7. Capability Recommendations

These recommendations are limited to the audited implementation. They do not add
new engine features.

### Keep

| Capability | Recommendation |
|---|---|
| Shared source-job architecture | Keep. It prevents duplicating audience traversal for every action and accurately reflects how the engine operates. The IGBot UI should make clear that sources can drive multiple enabled actions. |
| Followers, Followings, Blogger, and File sources | Keep. These are direct, understandable, and actively implemented. Distinguish direct `blogger` targets from file-backed targets. |
| Hashtag/Place Top and Recent modes | Keep while the corresponding Instagram navigation remains functional. Preserve the exact distinctions because each maps to a separate engine job. |
| `follow-percentage`, per-source limit, session limit, and end condition | Keep. These are the complete native Follow-control vocabulary. |
| Shared profile filtering | Keep. It centralizes candidate qualification and records skip reasons. |
| Interaction history and reinteraction delay | Keep. They are the engine's principal duplicate-processing protection. |
| Atomic consumption of file-backed sources | Keep. It supports durable queues when deletion-after-processing is enabled. |
| Follow verification and block detection | Keep. State verification after the click is necessary for reliable accounting. |

### Improve

| Capability | Recommendation |
|---|---|
| Source ownership in the UI | Improve terminology. Present these as shared interaction/audience sources, or explicitly disclose that enabling a Follow source activates an engine job shared with other actions. Do not imply source lists are Follow-exclusive. |
| `blogger` naming | Improve the UI label to “Specific Users” while retaining the engine key. The runtime behavior is direct-profile interaction, which is clearer than the historical engine term. |
| Limit terminology | Label `follow-limit` “Per-source Follow limit” and `total-follows-limit` “Per-session Follow limit.” Do not label either as a daily limit. |
| Filter defaults | Make the UI distinguish “key absent/inactive” from the example configuration's opinionated values. The example file is not the same as the runtime fallback. |
| Private/public filtering | Correct and regression-test `skip_if_public` upstream before relying on it. It currently tests the private state and therefore does not perform the behavior named by the key. |
| Maximum liker bound | Clarify or test the exclusive upper bound before exposing it as an inclusive “Maximum” field. |
| Source availability failures | Surface restricted lists, changed Instagram tabs, and navigation failures clearly in IGBot logs. These are common runtime limitations, not configuration validation errors. |
| File-backed targets | Keep the integrated editor, but preserve the exact `interact-from-file` filename/count contract and engine-generated `_not_found` behavior. |
| Fixed action ordering | Document Story → Like/Comment → DM → Follow in the UI/help. Current planned labels such as “Like after Follow” would contradict actual execution. |

### Remove or Do Not Expose as Working

| Capability | Recommendation |
|---|---|
| Legacy `interact` | Remove from new UI/config generation. The engine accepts but intentionally ignores it. |
| Legacy `hashtag-likers` | Remove from new UI/config generation. Use explicit Top/Recent keys. |
| `blogger-post-limits` | Do not present as functional until its runtime consumption is restored and tested. It is currently dead configuration. |
| Generic Keyword Search | Do not expose as an engine-backed Follow method. No matching runtime job exists. |
| Follow-specific Visit Profile, Scroll Profile, Like Random Posts, or Mute toggles | Do not map these to invented keys. Visit/scroll are intrinsic implementation details, Like is its own action, and Mute is absent. |
| Warmup, auto increment, daily limit, and dedicated Follow delay controls | Do not persist these as engine settings. The audited engine provides no such keys or behavior. They may remain visually planned only if they write nothing to engine configuration. |

## Audit Conclusion

The reliable redesign boundary is the existing source-job vocabulary plus the five
native Follow settings. The engine's Follow capability is mature in candidate
discovery, shared filtering, limits, UI-state verification, and interaction-history
tracking, but it is not an isolated module with its own source lists or behavioral
sub-options. A compatible IGBot Follow page must preserve that distinction and must
not translate planned controls into undocumented keys.
