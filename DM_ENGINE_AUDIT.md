# InstaAddict Direct Message Engine Audit

## Scope

This report audits the Direct Message (DM) implementation that currently exists in
InstaAddict. It describes observed code paths and configuration behavior only. No
runtime or application changes are proposed as part of this audit.

The main implementation points reviewed were:

- `InstaAddict/core/bot_flow.py`
- `InstaAddict/core/interaction.py`
- `InstaAddict/core/handle_sources.py`
- `InstaAddict/core/filter.py`
- `InstaAddict/core/session_state.py`
- `InstaAddict/core/storage.py`
- `InstaAddict/core/persistent_list.py`
- `InstaAddict/core/utils.py`
- `InstaAddict/plugins/core_arguments.py`
- all `InstaAddict/plugins/interact_*.py` source plugins
- `config-examples/config.yml`
- `config-examples/filters.yml`
- `config-examples/pm_list.txt`
- `ENGINE_CONFIG_MAP.md`

## Executive Summary

InstaAddict does not contain an independent DM job, DM queue, inbox processor, or
reply engine. DM is an optional action inside the shared profile-interaction
pipeline. Any enabled interaction source can supply a candidate, and that candidate
may receive a message when `pm-percentage`, the session PM limit, the shared profile
filters, and Instagram UI availability permit it.

The engine currently supports:

- probabilistic outbound messages to candidates from all shared interaction sources;
- targets supplied directly, through followers/followings/likers, hashtags, places,
  feed posts, or username files;
- a random message selected from `pm_list.txt`;
- spintax, emoji aliases, and escaped newlines in message templates;
- a per-session confirmed-message limit;
- optional termination of the whole session when that limit is reached;
- storage of the most recent interaction's `pm_sent` result and session DM totals.

It does not support:

- detecting new followers as a dedicated DM trigger;
- a persistent DM recipient queue;
- reading the inbox or conversation history;
- replying to incoming messages;
- automatic replies;
- AI-generated messages or prompts;
- a DM-specific configurable delay;
- sequential or round-robin message-template selection.

A material defect exists in the private/empty-profile gate: the runtime references
`profile_filter.can_pm_to_private_or_empty` without calling it. Because a bound
method is truthy, the configured `pm_to_private_or_empty` value is effectively
ignored in that branch.

## 1. DM Methods

### Architectural meaning of a “DM method”

There are no DM-specific source plugins. The engine's shared source plugins invoke
`interact_with_user()`, and DM is one possible action during that interaction. A
source therefore becomes a DM source only when `pm-percentage` is greater than zero.

The following table lists every active candidate path that reaches the shared DM
logic.

| Operator concept | Engine key(s) | Runtime implementation | Required target resource | Current status | Limitations |
|---|---|---|---|---|---|
| Message a named blogger/profile | `blogger` | `interact_blogger.py` -> `handle_blogger()` -> `interact_with_user()` | None beyond the configured username list | Used | DM is one probabilistic action; it is not a dedicated send-only operation. |
| Message a blogger's followers | `blogger-followers` | `interact_blogger_followers.py` -> `handle_followers()` -> `interact_with_user()` | None beyond configured source usernames | Used | This means followers of any configured source, not a purpose-built “new followers of my account” trigger. |
| Message a blogger's followings | `blogger-following` | Same plugin and handler family as blogger followers | None beyond configured source usernames | Used | Same shared filtering, interaction-history, probability, and session-limit gates. |
| Message likers of a blogger's posts | `blogger-post-likers`; scan depth also uses `blogger-post-limits` | `interact_blogger_post_likers.py` -> `handle_likers()` -> `interact_with_user()` | None beyond configured source usernames | Used | Candidate discovery is tied to post scanning; no DM-only mode. |
| Message users from a file | `interact-from-file` | `interact_blogger.py` -> `handle_blogger_from_file()` -> `interact_with_user()` | Configured username `.txt` source file | Used | The source file drives the complete interaction pipeline, not DM alone. |
| Message top/recent hashtag post owners | `hashtag-posts-top`, `hashtag-posts-recent` | `interact_hashtag_posts.py` -> `handle_posts()` -> `interact_with_user()` | Configured hashtags | Used | Subject to `interact-percentage` before normal profile actions. |
| Message top/recent hashtag post likers | `hashtag-likers-top`, `hashtag-likers-recent` | `interact_hashtag_likers.py` -> `handle_likers()` -> `interact_with_user()` | Configured hashtags | Used | No DM-specific control over which liker candidates are selected. |
| Message top/recent place post owners | `place-posts-top`, `place-posts-recent` | `interact_place_posts.py` -> `handle_posts()` -> `interact_with_user()` | Configured places | Used | Subject to the shared post-source selection rules. |
| Message top/recent place post likers | `place-likers-top`, `place-likers-recent` | `interact_place_likers.py` -> `handle_likers()` -> `interact_with_user()` | Configured places | Used | No DM-specific target history or queue. |
| Message owners of posts in the account's feed | `feed` | `interact_feed.py` -> `handle_posts()` -> `interact_with_user()` | Instagram feed | Used | Feed candidates bypass the normal prior-interaction check in `handle_posts()`, so repeat contact behavior differs from other sources. |

### Methods that do not exist

- **Message after follow:** there is no post-follow DM callback. On a normal public
  profile, DM is attempted before Follow.
- **Message after like or story as a distinct trigger:** likes and stories happen
  earlier in the same shared interaction, but their success does not enqueue or
  directly trigger DM.
- **Message new followers:** no code detects newly gained followers and builds a DM
  workload.
- **Message followers as a dedicated own-account operation:** `blogger-followers`
  can traverse a configured account's followers, but it is a generic source and has
  no “new follower” semantics.
- **DM-only file job:** `interact-from-file` can supply recipients, but it also runs
  the shared interaction pipeline.

No active DM method above is marked obsolete in the engine. The legacy accepted-but-
ignored keys `interact` and `hashtag-likers` are not working DM methods and should
not be treated as such.

## 2. Message Storage

### `pm_list.txt`

Path:

```text
accounts/<username>/pm_list.txt
```

Behavior:

- The file is read as UTF-8 each time a message is attempted.
- Blank lines are discarded.
- Each nonblank physical line is one complete message template.
- A single line produces a single available message.
- Multiple lines are selected with Python's `random.choice()`; selection is random,
  not sequential or round-robin.
- The selected line replaces the literal two-character sequence `\n` with a real
  newline.
- The result is expanded with `spintax.spin()`.
- The result is then passed through `emoji.emojize(..., use_aliases=True)`.
- The source line is not removed, marked used, or reordered after sending.

Consequences:

- Multiple physical lines represent multiple alternative messages, not one
  multiline message.
- A multiline message must use escaped `\n` within one physical line.
- The same template can be selected repeatedly.
- There is no per-recipient or per-session template sequence.
- Missing, unreadable, or empty files cause the send attempt to fail and return to
  the profile.

### `config.yml`

`config.yml` stores DM controls, not message bodies:

- `pm-percentage`
- `total-pm-limit`
- `end-if-pm-limit-reached`

### `filters.yml`

`filters.yml` stores `pm_to_private_or_empty`. Shared profile filters in this file
also gate whether a candidate reaches the DM action at all.

### Other storage

- `interacted_users.json` records general interaction history and a `pm_sent`
  boolean for the latest persisted interaction outcome.
- `sessions.json` records the confirmed `total_pm` count for each completed session.

Neither JSON file stores message content or acts as a pending-recipient queue.

## 3. DM Triggers

### Actual trigger

The only DM trigger is reaching the DM step of `interact_with_user()` for a candidate
supplied by an enabled shared interaction source.

A normal public-profile attempt requires:

1. The source plugin yields a candidate.
2. The source handler permits interaction, including blacklist and general
   reinteraction checks where that handler implements them.
3. `ProfileFilter.check_profile()` does not reject the candidate.
4. The candidate is not the running account itself.
5. The run is not in scrape-only mode.
6. `pm-percentage` resolves to a nonzero number.
7. The session PM limit is not reached.
8. A random integer from 1 through 100 is less than or equal to the resolved
   percentage.
9. Instagram exposes the expected Message/composer/send UI.
10. A message can be loaded from `pm_list.txt`.

For private or zero-post profiles, the DM attempt occurs in an earlier branch before
Follow. The code appears intended to add the `pm_to_private_or_empty` condition, but
the method is not called, so that configuration currently does not control runtime
behavior.

### What does not trigger DM

- A successful Follow does not trigger DM.
- A successful Like does not trigger DM.
- A successful Story view does not trigger DM.
- A newly gained follower does not trigger DM.
- An incoming message does not trigger DM.
- A database row or persistent queue does not trigger DM.

These actions can occur around the same candidate, but they are not causal DM
triggers.

## 4. Runtime Behavior and Settings

| Setting | Storage | Declared default | Actual behavior |
|---|---|---:|---|
| `pm-percentage` | `config.yml` | `"0"` | Parsed as an integer, float, or integer range. A range is randomly resolved when interaction values are initialized for a source run. For each candidate, a fresh 1-100 roll determines whether DM is attempted. Zero disables attempts. |
| `total-pm-limit` | `config.yml` | `"0"` | Parsed once into `current_pm_limit` for the session. It caps confirmed sends for the entire session, across all source jobs. Zero means the limit is already reached, effectively disabling DM even if `pm-percentage` is nonzero. Invalid syntax falls back to 10 in `SessionState.set_limits_session()`. |
| `end-if-pm-limit-reached` | `config.yml` | `false` | If true, reaching the PM cap contributes to the “active limits reached” condition and can stop further active jobs/the session. If false, further PMs are still blocked, but other eligible interaction actions/jobs may continue. |
| `pm_to_private_or_empty` | `filters.yml` | Example/map: `true`; missing field runtime result: `false` | Intended to control DM to private or empty profiles. Currently ineffective in the DM branch because `can_pm_to_private_or_empty` is referenced without `()`. |

### Limit accounting

- `SessionState.totalPm` starts at zero for each session.
- The counter increases only after the engine finds the exact posted message text and
  no longer sees the sending icon.
- A tap on Send without this UI confirmation does not consume the PM limit.
- The final count is written to `sessions.json` and included in console and optional
  Telegram reports.

### Delays

There is no DM-specific delay argument in the existing engine. Sending uses normal
UIAutomator waits, typing or paste behavior, keyboard handling, and a generic
`random_sleep()` only while a sending icon remains visible. No independently
configurable minimum/maximum DM delay exists.

### Private and empty profiles

- For a private profile, the engine opens profile Options and selects the exact
  `Send Message` action.
- For a public zero-post profile, it follows the normal Message-button path.
- The DM attempt precedes the optional Follow attempt in this branch.
- Because of the missing method call described above, the intended private/empty DM
  filter is not enforced.

### Message entry and confirmation

- The engine pastes text when the global `dont-type` option is enabled; otherwise it
  types the text.
- It clicks the composer Send control.
- It performs the existing block-detection check and closes the keyboard.
- Success requires finding the exact message text in the conversation and no active
  sending icon.
- Failures return `False`; there is no retry queue.

## 5. Replies

The audited engine does not implement:

- reading the Direct inbox;
- enumerating conversations;
- reading conversation history;
- detecting incoming messages;
- replying to incoming messages;
- automatic reply rules.

The only conversation-screen logic audited is the outbound composer flow reached
from a candidate's profile.

## 6. AI

No DM-related AI implementation exists in InstaAddict. The audited engine contains
no OpenAI/GPT integration, AI prompt store, generated-message path, or model-based
message selection. Messages come exclusively from `pm_list.txt` and are transformed
only by spintax and emoji expansion.

## 7. Queue and Database Behavior

### Candidate source

Recipients come directly from the currently running interaction source plugin. The
engine does not build a separate DM queue.

### `interacted_users.json`

This file is the general interaction history, not a follower database or DM queue.
For each username it can store:

- last interaction timestamp;
- following status and action flags;
- cumulative likes, story watches, and comments;
- the latest `pm_sent` boolean;
- session ID;
- originating job and target.

Most source handlers consult the last interaction timestamp and the global
`can-reinteract-after` setting before revisiting a user. This indirectly reduces
repeat DMs. The engine does not consult `pm_sent` as a dedicated “already messaged”
guard.

The `pm_sent` field is not cumulative: a later interaction that sends no PM can
replace `true` with `false`. It therefore describes the latest persisted interaction
outcome rather than reliable lifetime DM history.

### Feed exception

The feed handler explicitly allows candidates without the usual prior-interaction
check. As a result, feed-driven DM attempts do not have the same general reinteraction
protection as the other audited source handlers.

### No follower database or queue

There is no code path that compares follower snapshots, identifies new followers,
or creates a pending DM queue. `sessions.json` is historical reporting data only.

## 8. Resource Files

| Resource | Purpose | Format | Runtime usage |
|---|---|---|---|
| `accounts/<username>/config.yml` | Enables/probabilistically controls outbound DM, caps confirmed sends, optionally ends a session at the cap | YAML | Parsed into engine arguments before jobs run |
| `accounts/<username>/filters.yml` | Shared candidate filters plus intended private/empty-profile DM permission | YAML | Loaded by `Storage`/`Filter`; shared filters run before DM. The private/empty-specific flag is currently bypassed by a call-site defect. |
| `accounts/<username>/pm_list.txt` | Outbound message bank | UTF-8 plaintext; one template per nonblank physical line; `\n`, spintax, and emoji aliases supported | Read on every send attempt; one line chosen randomly |
| Configured source `.txt` files | Candidate usernames for `interact-from-file` | Plaintext usernames, one per line; config also specifies a count/range | Supplies candidates to the shared interaction pipeline; not DM-specific |
| `accounts/<username>/interacted_users.json` | General cross-module interaction history | JSON object keyed by username | Used for reinteraction timing and updated after interaction; stores latest `pm_sent` outcome |
| `accounts/<username>/sessions.json` | Completed session history | JSON array | Stores `total_pm` and other aggregate session metrics; not used to select recipients |

No other DM-specific resource file was found.

## 9. Complete Runtime Flow

```text
InstaAddict session loop
  -> build enabled job list
  -> optionally shuffle job order
  -> run the next shared interaction source plugin
  -> source discovers a candidate username
  -> blacklist and reinteraction checks (source-dependent)
  -> open candidate profile
  -> run shared ProfileFilter checks
  -> reject self or skipped profile
  -> private/empty branch OR normal public-profile branch
```

### Normal public profile

```text
Candidate accepted
  -> scrape-only check (scrape mode returns without DM)
  -> Story action attempt
  -> Like and Comment action attempts
  -> DM eligibility:
       pm-percentage != 0
       AND PM session limit not reached
       AND random roll passes
  -> restore profile scroll position if needed
  -> click Message
  -> load random pm_list.txt template
  -> expand escaped newlines, spintax, and emoji
  -> type/paste message
  -> click Send
  -> block detection and keyboard cleanup
  -> verify exact posted text and completed sending state
  -> increment totalPm only on confirmation
  -> return to profile
  -> Follow action attempt
  -> persist general interaction record, including latest pm_sent
```

### Private or zero-post profile

```text
Candidate accepted
  -> DM percentage/limit/random checks
  -> intended private/empty permission check
     (currently ineffective because the method is not called)
  -> open Send Message path
  -> load, send, and verify message
  -> optional Follow attempt
  -> persist general interaction record
```

### End of session

```text
Finish remaining eligible jobs or stop at an ending condition
  -> set session finish time
  -> persist sessions.json with total_pm
  -> include PM count in reports
```

## 10. Verified Limitations and Defects

1. **Private/empty filter bypass.** The condition uses
   `profile_filter.can_pm_to_private_or_empty` instead of
   `profile_filter.can_pm_to_private_or_empty()`. The setting is therefore not
   enforced.
2. **No dedicated DM method.** DM cannot be scheduled or sourced independently from
   the shared interaction jobs.
3. **No new-follower trigger.** Generic follower traversal is not equivalent to
   detecting newly gained followers.
4. **No queue.** Failed sends are not retained for retry and candidates are not
   queued independently.
5. **No reply support.** The engine never reads inbox conversations.
6. **No AI support.** Message content is file-based only.
7. **No DM-specific delay.** Only framework/UI waits apply.
8. **Latest-result history only.** `pm_sent` can be reset by a later non-DM
   interaction and is not used as a dedicated duplicate-send guard.
9. **Source-dependent deduplication.** Feed candidates bypass the normal prior-
   interaction check.
10. **Message verification is UI-text dependent.** A send is counted only when the
    exact message text is found and the sending icon is absent; UI changes or text
    rendering differences can produce false failures.
11. **Misleading missing-message warning.** The warning says “If you don't want to
    comment” even though it is handling PM configuration.
12. **Physical-line template constraint.** Literal multiline entries in the file
    become separate templates; multiline messages require escaped `\n`.

## 11. Recommendations

These recommendations are restricted to retaining, correcting, or removing aspects
of the audited implementation. They do not add capabilities that the engine does not
already have.

| Capability | Keep | Improve | Remove |
|---|---|---|---|
| Shared-source DM action | Keep the compatibility behavior whereby all active profile sources can attempt DM. | Make the coupling explicit in configuration/UI documentation and test every source path consistently. | Do not present nonexistent standalone DM jobs as engine capabilities. |
| `pm-percentage` | Keep as the existing probabilistic outbound-message control. | Validate the effective range as 0-100 and document when a configured range is resolved. | None. |
| `total-pm-limit` | Keep the confirmed-send per-session cap. | Make the zero-disabled semantics and invalid-value fallback unambiguous. | None. |
| `end-if-pm-limit-reached` | Keep because it independently controls whether the PM cap ends active work or only suppresses further DMs. | Clarify that it does not change the cap itself. | None. |
| Private/empty permission | Keep the existing `pm_to_private_or_empty` capability. | Correct the missing method invocation and add regression coverage for true, false, and missing values. | Remove the current ineffective call-site behavior, not the setting. |
| `pm_list.txt` message bank | Keep random selection, spintax, emoji aliases, and escaped-newline compatibility. | Correct the missing-file warning and document the one-physical-line-per-template rule. | None. |
| Outbound send confirmation | Keep confirmation before incrementing `totalPm`. | Harden verification against UI variation while preserving confirmed-send accounting. | None. |
| General interaction history | Keep `interacted_users.json` as cross-module history. | Preserve historical PM truth rather than overwriting `pm_sent`, or clearly define it as latest-attempt state; make feed behavior consistent with the intended reinteraction policy. | Do not treat `pm_sent` as a queue or reliable lifetime record in its current form. |
| Session reporting | Keep `total_pm` in `sessions.json`, console reports, and Telegram reports. | Ensure failed confirmation and actual-send discrepancies are diagnosable. | None. |
| DM delay | Keep the current absence of a dedicated setting accurately documented. | None within the audited capability set. | Remove any UI/config claim that the current engine supports a dedicated DM delay. |
| Replies and AI | None; these capabilities do not exist in the audited engine. | None within this audit. | Remove or label any claim that InstaAddict currently reads/replies to DMs or generates AI messages. |

## Conclusion

The existing InstaAddict DM engine is a compact outbound-message action embedded in
the common interaction pipeline. Its reliable compatibility surface consists of
three `config.yml` keys, one `filters.yml` key, the `pm_list.txt` message bank, shared
source/profile filtering, confirmed-send session accounting, and general interaction
history. It should not be modeled as a standalone messaging system: there is no DM
scheduler, follower-event trigger, inbox reader, reply processor, AI layer, or
persistent recipient queue in the audited implementation.
