# InstaAddict Global Engine Settings Audit

## Purpose and Scope

This document audits the global and session-wide configuration surface of the bundled InstaAddict engine used by IGBot. It is based on the argument registry and the runtime code that consumes those arguments, not only on example configuration files.

The engine does not have a separate global configuration file. Nearly every persistent option is stored in an individual account's `config.yml`, even when it controls the entire engine process or session. In this report:

- **Global** means the value affects the whole engine invocation or session rather than one interaction module.
- **Account specific** means the value identifies the selected account/device or configures a particular module, even though the engine reads it during startup.
- **Runtime only** means the value is supplied to the process and is not an account setting.

The audited implementation is primarily in:

- `InstaAddict/plugins/core_arguments.py`
- `InstaAddict/core/config.py`
- `InstaAddict/core/bot_flow.py`
- `InstaAddict/core/session_state.py`
- `InstaAddict/core/utils.py`
- `InstaAddict/core/filter.py`
- `InstaAddict/core/decorators.py`
- `InstaAddict/plugins/cloned_app.py`
- `InstaAddict/plugins/data_analytics.py`
- `InstaAddict/plugins/telegram.py`

## Executive Findings

- Global behavior is configured per account. There is no engine-owned cross-account global settings store.
- The core global controls are active and broadly reusable, but several expose legacy command-line terminology rather than stable application concepts.
- `disable-block-detection` has inverted parser semantics. Its effective default is to run block detection; setting the option disables it.
- `total-comments-limit`, `total-pm-limit`, and `total-scraped-limit` have parser defaults that disagree with fallback defaults in `SessionState.set_limits_session()`.
- `analytics` is registered as an operation but its implementation is deliberately disabled and does not generate a report.
- `uia-version`, `interact`, and `hashtag-likers` are legacy or deprecated.
- `move-folders-in-accounts` is a one-time migration control, not a normal runtime setting, and its invocation guard is defective in the audited flow.
- The engine still accepts a deprecated `filter.json` fallback when `filters.yml` is absent.
- Unknown configuration keys are fatal only on the first parse. Later parsing can retain unknown arguments without the same failure path.
- Job order is derived from the physical order of operation keys in `config.yml`; `shuffle-jobs` overrides that order for a session.

## General

| Setting | Default | Location | Scope | Purpose and actual runtime behavior | Assessment |
|---|---:|---|---|---|---|
| `config` / `--config` | None | Command line | Runtime only | Selects the YAML file parsed by `configargparse`. The file is opened with `r+` even though parsing itself is read-only. Only `.yml` and `.yaml` paths are accepted. | **Keep**, but improve by opening read-only and keeping file mutation outside parsing. |
| `username` | None, required for account operation | `config.yml` | Account specific | Selects the Instagram username. At runtime the engine opens Instagram, navigates to the account, attempts to switch to this username, and aborts that session if it cannot. | **Keep**. It is account identity, not a global preference. |
| `device` | None | `config.yml` | Account specific | Supplies the ADB serial used by device creation and shell commands. When absent, ADB commands may run without `-s`, relying on a single connected device. | **Keep**, but explicit device assignment is required for safe multi-phone operation. |
| `app-id` | `com.instagram.android` | `config.yml` | Account specific | Selects the Android package opened, stopped, inspected, and excluded from `close-apps`. `Config` also reads legacy `app_id` as an undocumented compatibility alias. | **Keep**. Improve by treating `app_id` only as a migration alias. |
| `use-cloned-app` | `false` | `config.yml` | Account specific | If MIUI displays its original/cloned-app chooser, selects item 2 instead of item 1. It does not discover packages or create clones. | **Keep** only for devices that use this MIUI chooser; otherwise the explicit `app-id` is clearer. |
| `speed-multiplier` | `1` | `config.yml` | Global | Divides most modulable random sleep durations. A floor of 0.3 seconds remains. Non-modulable waits ignore it. | **Keep**, but validate positive non-zero numeric values. |
| `allow-untested-ig-version` | `false` | `config.yml` | Global | When Instagram is newer than the tested version, suppresses the interactive acknowledgement prompt. It does not make an untested version compatible. Version retrieval errors are logged and execution continues. | **Keep**, but improve the name and make unattended behavior explicit. |

## Working Hours and Scheduler

| Setting | Default | Location | Scope | Purpose and actual runtime behavior | Assessment |
|---|---:|---|---|---|---|
| `working-hours` | `["00.00-23.59"]` | `config.yml` | Global | Defines one or more allowed windows in engine `HH.MM-HH.MM` format. The engine checks the window before a session and before every job. Outside a window it waits until the next start. Overnight windows are supported by the range calculation. | **Keep**. This is the authoritative engine schedule. |
| `time-delta` | `"0"` | `config.yml` | Global | At the beginning of each session cycle, resolves a fixed/ranged value, randomly gives it a positive or negative sign, converts it to minutes, then adds 0–59 seconds. The resulting offset shifts every working-hours boundary for that cycle. | **Improve**. The random sign and extra seconds are undocumented behavior and make exact schedules non-deterministic. |
| `repeat` | None | `config.yml` | Global | When set, keeps the engine loop alive and sleeps the resolved number of minutes before another session if still inside working hours. Outside working hours, the working-hours wait takes precedence. Without it, the process finishes after one session. | **Keep** for the legacy runtime; IGBot's phone scheduler should own repetition long term. |
| `total-sessions` | `-1` | `config.yml` | Global | Limits repeated sessions; `-1` means unlimited. It has no practical effect unless `repeat` is enabled. The value may be resolved through the engine's range parser even though the registry describes it as an integer. | **Improve** by validating its dependency on `repeat` and using one consistent type. |
| `shuffle-jobs` | `false` | `config.yml` | Global | Randomly permutes enabled jobs once per session. Otherwise job order follows operation-key order in `config.yml`, not plugin registration order. Reporting operations are removed from the shuffled job list and handled at session end. | **Keep**, but document the otherwise hidden dependence on YAML key order. |

### Scheduler behavior not represented by a setting

- A session remains inside a single account process; the bundled engine has no global multi-account scheduler.
- The working-hours check occurs before device/session initialization and again before each enabled job.
- `00.00-23.59` is effectively always available, not disabled.
- Repetition sleeps synchronously in the engine process and is interruptible only through the engine's stop path.

## Interaction and Session Limits

These controls are global to one account session even though some limits are named after modules.

| Setting | Default | Location | Scope | Purpose and actual runtime behavior | Assessment |
|---|---:|---|---|---|---|
| `total-interactions-limit` | `"1000"` | `config.yml` | Global | Resolves a per-session cap across all recorded interaction attempts. Reaching it unconditionally ends further jobs. | **Keep**. |
| `total-successful-interactions-limit` | `"100"` | `config.yml` | Global | Resolves a per-session cap across successful interactions. Reaching it unconditionally ends further jobs. Scraped users also increment successful-interaction counters in `SessionState.add_interaction()`. | **Improve** because scrape accounting changes the meaning of “successful interactions.” |
| `total-scraped-limit` | `"50"` | `config.yml` | Global | Caps successful scraped users and participates in the unconditional overall-stop result. In scrape mode the engine gathers data instead of interacting. | **Keep**, but fix the default mismatch: runtime fallback is `200`. |
| `total-likes-limit` | `"300"` | `config.yml` | Account specific | Resolves the session Like cap. Like actions check it directly. It ends the entire active-job sequence only when its matching end flag is true. | **Keep** as a module limit. |
| `total-follows-limit` | `"50"` | `config.yml` | Account specific | Resolves the session Follow cap. Follow actions check it directly. It ends the active-job sequence only when its matching end flag is true. | **Keep** as a module limit. |
| `total-unfollows-limit` | `"50"` | `config.yml` | Account specific | Resolves the session Unfollow cap. Once reached, remaining unfollow jobs are skipped independently of the active-job end flags. | **Keep**, but document its different stop semantics. |
| `total-watches-limit` | `"50"` | `config.yml` | Account specific | Resolves the session Story watch cap. It ends the active-job sequence only when its matching end flag is true. | **Keep** as a module limit. |
| `total-comments-limit` | `"0"` | `config.yml` | Account specific | Resolves the session Comment cap. With the registered default of zero, Comment is immediately at its limit. `SessionState` uses `10` only if parsing the configured value fails. | **Improve** by eliminating the conflicting fallback and documenting zero as disabled. |
| `total-pm-limit` | `"0"` | `config.yml` | Account specific | Resolves the session DM cap. With the registered default of zero, DM is immediately at its limit. `SessionState` uses `10` only if parsing fails. | **Improve** by eliminating the conflicting fallback and documenting zero as disabled. |
| `end-if-likes-limit-reached` | `false` | `config.yml` | Account specific | Causes a reached Like cap to block subsequent active jobs and possibly end the job loop. | **Keep**, but the interaction with the total limit should be clearer. |
| `end-if-follows-limit-reached` | `false` | `config.yml` | Account specific | Causes a reached Follow cap to block subsequent active jobs and possibly end the job loop. | **Keep**. |
| `end-if-watches-limit-reached` | `false` | `config.yml` | Account specific | Causes a reached Story cap to block subsequent active jobs and possibly end the job loop. | **Keep**. |
| `end-if-comments-limit-reached` | `false` | `config.yml` | Account specific | Causes a reached Comment cap to block subsequent active jobs and possibly end the job loop. | **Keep**. |
| `end-if-pm-limit-reached` | `false` | `config.yml` | Account specific | Causes a reached DM cap to block subsequent active jobs and possibly end the job loop. | **Keep**. |

### Shared source controls

These apply to the common interaction/source pipeline rather than to one particular action. They are global for the current account session.

| Setting | Default | Location | Scope | Purpose and actual runtime behavior | Assessment |
|---|---:|---|---|---|---|
| `interact-percentage` | `"50"` | `config.yml` | Global | Chance to interact with the owner of a post found through hashtag/place-style sources. | **Keep**, but expose only where those sources are used. |
| `interactions-count` | `"30-50"` | `config.yml` | Global | Successful-interaction target for each blogger/source run. | **Keep**. |
| `skipped-list-limit` | `"10-15"` | `config.yml` | Global | Stops scanning the current list/source after too many skipped candidates. | **Keep** as an advanced safety/performance setting. |
| `skipped-posts-limit` | `"5"` | `config.yml` | Global | Stops scanning the current post source after too many skipped posts. | **Keep** as an advanced setting. |
| `fling-when-skipped` | `"0"` | `config.yml` | Global | Switches from ordinary scrolling to a fling after the configured number of skips. Its own help text discourages use. | **Remove** from normal UI; retain only for legacy compatibility. |
| `can-reinteract-after` | None | `config.yml` | Global | Allows a previously handled user to become eligible again after a resolved number of hours. | **Keep**. |
| `truncate-sources` | `"0"` | `config.yml` | Global | Limits/truncates source lists before processing; zero leaves them untruncated. | **Keep** as an advanced source control. |
| `scrape-to-file` | None | `config.yml` | Global | Places active jobs in scrape-only mode and writes discovered users instead of performing interactions. It is explicitly skipped for unfollow jobs. | **Keep**, but separate clearly from automation mode. |
| `delete-interacted-users` | `false` | `config.yml` | Global | Removes processed usernames from applicable source files. This mutates input resources during execution. | **Improve** with clear destructive semantics and atomic file handling. |

## Safety

| Setting | Default | Location | Scope | Purpose and actual runtime behavior | Assessment |
|---|---:|---|---|---|---|
| `disable-block-detection` | Effective parser default `true` | `config.yml` | Global | Registered with `action="store_false"`. The runtime performs toast-based block detection when the parsed attribute is true and skips detection when false. Consequently, absence of the option enables detection; specifying the disabling option turns it off. | **Improve urgently**. The name, config value, parser action, and runtime condition are easy to interpret incorrectly. Use a normalized positive concept in IGBot while preserving compatibility. |
| `total-crashes-limit` | `"5"` | `config.yml` | Global | Resolves a session crash limit. Decorated operation failures increment the count and stop the bot when the limit is reached. | **Keep**. |
| `count-app-crashes` | `false` | `config.yml` | Global | Controls whether failures classified as application crashes increment the crash count. “Normal” crashes are counted regardless. | **Keep**, but document the engine's crash categories. |
| `disable-filters` | `false` | `config.yml` | Global | Bypasses loading `filters.yml`; profile checks then proceed without configured conditions. The warning says documentation defaults are used, but the implementation actually leaves conditions unset and returns permissive results in several paths. | **Improve** because the warning does not accurately describe runtime behavior. |
| `allow-untested-ig-version` | `false` | `config.yml` | Global | Suppresses the interactive version-risk acknowledgement. It neither changes selectors nor prevents version-related failures. | **Keep**, with clearer unattended-operation wording. |

### Unconfigured safety behavior

The engine always disables Android heads-up notifications at session start and re-enables them at normal finish/stop. There is no setting controlling this device-wide mutation.

## Device and Performance

| Setting | Default | Location | Scope | Purpose and actual runtime behavior | Assessment |
|---|---:|---|---|---|---|
| `screen-sleep` | `false` | `config.yml` | Global | Turns the device screen off after the session finishes. The next loop wakes and unlocks it. | **Keep**. |
| `screen-record` | `false` | `config.yml` | Global | Starts uiautomator2 recording after Instagram opens, stops it when Instagram closes, and attempts to preserve/restart recordings around crashes. Missing image dependencies are logged rather than fatal. | **Keep** as a diagnostic option, but improve dependency and output-path reporting. |
| `close-apps` | `false` | `config.yml` | Global | Stops all running Android applications except the selected Instagram package after Instagram is ready. | **Keep** as an opt-in interference-control setting; its broad device impact must be explicit. |
| `restart-atx-agent` | `false` | `config.yml` | Global | Before each session, restores the keyboard, kills `atx-agent`, then starts `/data/local/tmp/atx-agent server -d` through ADB. Failures are logged and execution continues. | **Improve**. It relies on shell commands and a fixed device-side path without validating recovery. |
| `kill-atx-agent` | `false` | `config.yml` | Global | Kills `atx-agent` at normal session end, while waiting outside working hours, and during stop. It also restores the keyboard first. | **Keep** only as an advanced lifecycle option. |
| `dont-type` | `false` | `config.yml` | Global | Uses paste mode instead of typed input for comments and private messages. The negative name hides its actual behavior. | **Improve** by presenting it as an input-mode choice. |
| `speed-multiplier` | `1` | `config.yml` | Global | Affects shared randomized sleeps but not waits marked non-modulable. | **Keep**, with strict validation and a documented safe range. |

## Logging, Reporting, and Diagnostics

| Setting | Default | Location | Scope | Purpose and actual runtime behavior | Assessment |
|---|---:|---|---|---|---|
| `debug` | `false` | `config.yml` | Global | Enables debug log verbosity through startup configuration and skips the ten-second pre-job countdown. It therefore changes both logging and timing. | **Keep**, but separate verbosity from countdown behavior in a future compatibility layer. |
| `screen-record` | `false` | `config.yml` | Global | Records the device screen for diagnostics and crash evidence. | **Keep**, subject to the dependency caveat above. |
| `telegram-reports` | `false` | `config.yml` | Account specific | Registered as an operation so its position is discovered from the config. It is removed from normal jobs, captures end-of-session profile counts, loads `sessions.json` and `telegram.yml`, then sends a summary through Telegram's HTTP API. | **Keep**, but treat credentials as secrets and avoid synchronous network calls in the runtime path. |
| `telegram-api-token` | Placeholder / none usable | `telegram.yml` | Account specific | Bot token supplied to Telegram `sendMessage`. Missing config or failed requests are logged. | **Keep**, but protect it as a credential. |
| `telegram-chat-id` | Placeholder / none usable | `telegram.yml` | Account specific | Destination chat identifier for the end-of-session report. | **Keep**. |
| `analytics` | `false` | `config.yml` | Account specific | Registered as an operation and deferred until session end. The plugin only logs that analytics was removed and does not generate a report. | **Remove** from active configuration/UI until the implementation exists. This is a confirmed runtime defect/stub. |

## Hooks and Storage

| Setting | Default | Location | Scope | Purpose and actual runtime behavior | Assessment |
|---|---:|---|---|---|---|
| `pre-script` | None | `config.yml` | Global | Runs the referenced local executable/script synchronously before every session and waits for it to finish. Missing paths and launch exceptions are logged; no timeout is enforced. | **Improve**. It can block indefinitely and executes arbitrary local code. |
| `post-script` | None | `config.yml` | Global | Runs synchronously after normal session cleanup and waits for completion. It is not guaranteed on every abnormal exit path. | **Improve** with timeout and explicit failure semantics. |
| `move-folders-in-accounts` | `false` | `config.yml` | Global | Intended as a one-time migration that moves root-level username directories under `accounts/`. It is evaluated before normal config/runtime initialization. The audited guard checks membership against the parsed namespace rather than the boolean attribute, which is not a valid `argparse.Namespace` usage. | **Remove** from normal runtime. It is legacy migration behavior with a defective invocation guard and broad filesystem impact. |

### Engine-managed files with global/session relevance

| File | Scope | Runtime role | Assessment |
|---|---|---|---|
| `accounts/<username>/sessions.json` | Account specific | Persistent session history used by reports. | **Keep**. |
| `accounts/<username>/filters.yml` | Account specific | Shared profile qualification rules loaded by the session's `Filter`. | **Keep**. |
| `accounts/<username>/filter.json` | Account specific | Deprecated fallback accepted when the storage path points to JSON. A warning says support will stop. | **Remove** after one-time migration to `filters.yml`. |
| `accounts/<username>/telegram.yml` | Account specific | Stores Telegram credentials for reports. | **Improve** credential protection. |
| `crashes/<version_timestamp>/...` | Global | Crash screenshots, hierarchy dumps, and related diagnostics. | **Keep**, with retention controls outside this audit. |

## Legacy and Obsolete Settings

| Setting | Default | Location | Scope | Actual status | Assessment |
|---|---:|---|---|---|---|
| `uia-version` | `2` | `config.yml` | Global | Registered by core arguments and explicitly described as deprecated. No meaningful runtime selection was found in the audited flow. | **Remove** from UI and new configs; accept only for legacy parsing if required. |
| `interact` | None | `config.yml` | Account specific | Registered but `_is_legacy_arg()` warns and excludes it from enabled jobs. | **Remove** from configs. |
| `hashtag-likers` | None | `config.yml` | Account specific | Registered but `_is_legacy_arg()` warns and excludes it from enabled jobs. Superseded by top/recent variants. | **Remove** from configs. |
| `detect-block` | Not registered | legacy `config.yml` | Global | Explicitly rejected as unknown; the parser tells operators to replace it with `disable-block-detection`. | **Remove**. It is a migration-only alias, not supported configuration. |
| `app_id` | `com.instagram.android` fallback | legacy `config.yml` | Account specific | Read only during config preloading as a backward-compatible alias for `app-id`; it is not a registered engine key. | **Remove** after migration to `app-id`. |

## Duplicate and Overlapping Controls

The following are not exact duplicate keys, but their runtime responsibilities overlap and can produce confusing combinations:

- Module totals (`total-likes-limit`, `total-follows-limit`, and peers) are enforced alongside `total-interactions-limit` and `total-successful-interactions-limit`. Whichever threshold is reached first wins.
- Module `end-if-*-limit-reached` flags affect whether a reached module limit ends other active jobs, while overall interaction/success/scrape limits always stop them. Unfollow uses a third behavior: subsequent unfollow jobs are skipped without an end flag.
- `follow-limit` is a per-source Follow cap, whereas `total-follows-limit` is the per-session cap. Their similar names obscure the scope difference.
- `repeat`, `total-sessions`, and `working-hours` jointly govern lifecycle. `total-sessions` alone does not cause repetition.
- `debug` controls both log verbosity and the pre-job countdown.
- `restart-atx-agent` first performs the same kill behavior as `kill-atx-agent`, but the two settings govern different lifecycle points.
- `app-id` and the unregistered legacy `app_id` alias describe the same value.

## Runtime Defects and Undocumented Behavior

1. **Block-detection inversion** — `disable-block-detection` uses `store_false`, while the runtime detects blocks when the resulting attribute is true. The default therefore enables detection, contrary to a literal reading of the key and contrary to the current note in `ENGINE_CONFIG_MAP.md`.
2. **Limit default mismatches** — registry defaults are `0` for comments, `0` for PM, and `50` for scraping; invalid-value fallbacks in `SessionState` are respectively `10`, `10`, and `200`.
3. **Analytics is non-functional** — the registered plugin is a warning stub and produces no report.
4. **Migration guard defect** — `bot_flow.py` tests `"--move-folders-in-accounts" in configs.args`; the parsed namespace is not a normal iterable flag collection. The setting is unsafe to regard as a functioning runtime option.
5. **Misleading filter warning** — when filters are disabled, the engine says documentation defaults are used, but it leaves filter conditions unloaded and takes permissive/no-filter paths.
6. **YAML order changes execution** — enabled operation order is reconstructed by scanning raw config lines. Reordering keys can reorder jobs even though YAML mappings are normally treated as semantic mappings.
7. **Unknown-key handling differs by parse phase** — unknown arguments trigger an abort only when `first_run` is true.
8. **Config parser requests write access** — the config file open callback uses `r+` even though argument parsing does not need to write.
9. **Pre/post hooks are unbounded** — both wait synchronously with no timeout; a hung hook stalls the engine.
10. **Device notification state is mutated globally** — heads-up notifications are disabled and later re-enabled without preserving the device's original value.
11. **Interactive untested-version prompt** — unattended execution can block on `input()` unless `allow-untested-ig-version` is set.
12. **Version comparison is lexical by tuple element** — version components are compared as strings, not integers, which can misorder values such as `10` and `9`.

## Configuration Boundary: Not Global Settings

For completeness, the following registered families are intentionally not enumerated as global settings because they belong to individual automation modules or target sources:

- Source operations such as `blogger-followers`, `blogger-following`, hashtags, places, feed, and file-driven operations.
- Follow, Unfollow, Like, Story, Comment, and DM percentages, counts, delays, and resource lists, except their session-wide totals documented above.
- Profile and content filters in `filters.yml`; these are account-specific qualification policy even though several modules share them.
- `comments_list.txt` and `pm_list.txt`; these are account-specific content resources.

Their complete registered vocabulary remains documented in `ENGINE_CONFIG_MAP.md`.

## Disposition Summary

### Keep

- Account/device/application identity controls.
- Working hours and the legacy repetition controls while the bundled runtime remains in use.
- Session-wide limits and crash protection.
- Device lifecycle controls where their broad effects are made explicit.
- Shared source controls that are actively consumed.
- Telegram reporting, with credential handling improvements.

### Improve

- Normalize the inverted block-detection setting at the IGBot compatibility boundary.
- Reconcile parser defaults with runtime fallbacks.
- Separate debug verbosity from countdown timing.
- Validate ranges and cross-setting dependencies.
- Make hooks bounded and failure-aware.
- Clarify destructive input-file mutation and device-wide side effects.
- Replace misleading filter-disabled messaging with actual behavior.

### Remove

- `uia-version` from new configuration and UI.
- Legacy `interact`, `hashtag-likers`, `detect-block`, and `app_id` after migration.
- `analytics` as a presented working option while its plugin remains a stub.
- `move-folders-in-accounts` from the ordinary runtime path.
- Deprecated `filter.json` after migration to `filters.yml`.

