# IGBot Runtime Architecture

## Status and Purpose

This document is the master specification for the future IGBot runtime. It defines
the intended operator-facing behavior independently of InstaAddict's current
execution model. It is an architecture specification, not an implementation plan
or a description of completed runtime functionality.

The IGBot runtime owns scheduling, limits, recovery, runtime hooks, state,
statistics, and module coordination. InstaAddict remains a temporary execution
provider behind a compatibility boundary while IGBot replaces legacy behavior in
controlled stages.

## 1. Runtime Overview

### Execution hierarchy

```text
Fleet Runtime
  -> one Phone Scheduler per started phone
       -> one active Account Session at a time
            -> Session Startup
            -> Smart Interaction Scheduler
                 -> interaction modules
                 -> inline Runtime Hooks
                 -> Runtime Recovery when a failure occurs
            -> Session Shutdown
       -> wait for the next eligible account session
```

The phone is the unit the operator starts and stops. A started phone owns one
persistent Phone Scheduler. The scheduler remains alive while no account is
eligible and wakes when a schedule, configuration, or stop event requires it.

Only one account session may control a phone at a time. Only one Android UI action
may be active on that phone at a time. Different phones may run concurrently and
must not share mutable session state.

### Complete lifecycle

```text
Operator starts phone
  -> validate managed phone and ADB state
  -> start Phone Scheduler
  -> load active accounts and schedules
  -> select next eligible account
  -> create Account Session
  -> run Session Startup
  -> run Smart Interaction Scheduler
  -> execute Runtime Hooks inline when module events trigger them
  -> invoke Runtime Recovery only when a failure occurs
  -> stop at schedule end, operator request, safety stop, or completed session
  -> run Session Shutdown
  -> return control to Phone Scheduler
  -> select another eligible account or wait
```

### Runtime state ownership

The runtime exposes explicit states rather than inferring state from processes or
buttons.

- Phone Scheduler: `Stopped`, `Starting`, `Waiting`, `Running`, `Stopping`, `Error`.
- Account Session: `Pending`, `Starting`, `Running`, `Paused`, `Recovering`,
  `Stopping`, `Completed`, `Failed`, `Cancelled`.
- Account availability: `Ready`, `Scheduled`, `Paused`, `Blocked`,
  `WaitingForOperator`, `Archived`.
- Module: `Disabled`, `Ready`, `Running`, `CoolingDown`, `LimitReached`, `Blocked`,
  `Failed`.
- Runtime Hook invocation: `Triggered`, `Running`, `Completed`, `Failed`.

State changes are published as events to the UI, audit log, statistics store, and
future synchronization layer. The UI displays runtime state but does not calculate
or own it.

### RuntimeContext ownership

`SessionController` creates exactly one `RuntimeContext` after a session has been
admitted. `SessionContext` remains its immutable identity record; `RuntimeContext`
owns the session-scoped references and evolving runtime state used during
execution.

```text
SessionController
  -> creates RuntimeContext
  -> StartupPipeline receives RuntimeContext
       -> every Startup Stage receives the same RuntimeContext
  -> StartupResult is attached to RuntimeContext
  -> Smart Interaction Scheduler receives the same RuntimeContext
       -> Modules and Runtime Hooks receive the same RuntimeContext
       -> Runtime Recovery receives the same RuntimeContext when required
  -> Session Shutdown receives the same RuntimeContext
  -> context lifetime ends with the Account Session
```

Runtime components receive `RuntimeContext` instead of separate account, phone,
settings, logger, and state parameters. The context grows only through explicit
typed runtime references as later subsystems are implemented. It is never global,
never shared between Account Sessions, and never used concurrently by different
phones.

`RuntimeLogger` is a provider-independent reference owned by `RuntimeContext`. All
native runtime components log through its `debug`, `info`, `warning`, and `error`
interface. Console, Runtime UI, notification, file, and Backend API destinations
are future adapters; runtime components neither select nor write to those
destinations directly.

### Stop semantics

Stop is cooperative and phone-scoped:

1. Reject new module work and new Runtime Hook invocations.
2. Cancel the current action at the nearest safe boundary.
3. Ask the execution provider to stop gracefully.
4. Restore temporary device state owned by the session.
5. Persist final counters and the cancellation reason.
6. terminate the Account Session and Phone Scheduler.

A bounded forced cleanup may follow a failed graceful stop, but it must be recorded
as a recovery event. Stopping one phone must never stop another phone.

## 2. Session Startup

Session Startup is an ordered pipeline. Interaction modules cannot run until all
mandatory gates succeed or an explicit policy permits a degraded session.

### Startup order

Phone ownership, authoritative configuration loading, assignment validation, and
the immutable session snapshot are Account Session admission requirements. They
complete before the following startup pipeline begins:

1. **Wait for Internet availability.** Test Internet connectivity before changing
   network state or launching Instagram. If unavailable, wait 60 seconds and retry
   automatically. Repeat until connectivity is restored or the operator stops the
   phone; no operator action is required.
2. **Toggle Airplane Mode Between Sessions.** When enabled, AirplaneModeController
   performs one verified Airplane Mode on/off cycle. It does not wait for Internet
   restoration; Internet availability and retry timing belong exclusively to
   InternetChecker.
3. **Launch Instagram.** Validate the assigned Application ID, open that package,
   and establish the Android automation connection.
4. **Wait After Launch.** Apply the configured launch delay before inspecting the
   application.
5. **Verify the correct account.** Confirm that the visible Instagram account is
   the scheduled account. Detect login challenges and perform bounded account
   selection or login recovery when required.
6. **Run Follower Synchronization.** Perform exactly one follower scan. Compare it
   with durable per-account interaction state, update Follow Back Ratio facts,
   identify newly gained followers, and update the follower snapshot.
7. **Build the Startup Result.** Produce the immutable scheduler input describing
   follower synchronization, newly gained followers, enabled modules, module
   budgets, limit balances, target readiness, cooldowns, and health state.
8. **Enter the Smart Interaction Scheduler.** Hand the Startup Result to the
   scheduler and begin module selection.

InternetChecker is startup stage one. It depends only on the platform-independent
NetworkProvider interface and the session RuntimeContext. When the provider reports
no Internet, InternetChecker emits `No Internet connection. Retrying in 60
seconds...` through RuntimeLogger, waits exactly 60 seconds, and checks again. This
loop is normal startup behavior: it is not a failure, recovery event, or account
error, and no later startup stage or scheduler entry may run until connectivity is
restored.

AndroidNetworkProvider owns the Android/ADB reachability probe behind the
NetworkProvider boundary. InternetChecker never imports or invokes Android APIs,
ADB, InstaAddict, UI automation, or platform subprocesses.

AirplaneModeController likewise depends on a platform-neutral AirplaneModeProvider.
For authorized, developer-managed Samsung Android 11+ phones, the production
Android provider uses the connectivity service shell command (`cmd connectivity
airplane-mode enable|disable`) and queries the same service after each transition.
This is preferred over writing `Settings.Global` directly because applications
cannot write that protected setting and changing the stored flag alone is not a
verified radio transition. A Settings Intent only displays the operator-facing
Airplane Mode settings screen; it does not toggle the setting. UIAutomator can
drive that screen but is not the primary mechanism because it depends on visible
OEM UI, localization, device unlock state, and instrumentation. Samsung firmware,
carrier policy, or enterprise policy may still reject the shell command, so both
transitions must be verified and a rejection must fail the startup stage rather
than silently falling back to UI interaction.

Every startup item executes exactly once for that Account Session. Follower
Synchronization is the only startup follower scan: FBR calculation and new-follower
detection are outcomes of the same scan, never separate passes. Internet waiting,
account verification, launch work, and Follower Synchronization are startup stages,
not Runtime Hooks and not scheduler modules.

Failures are classified as fatal, retryable, or optional. A missing Application ID
or wrong account is fatal after its recovery policy is exhausted. A temporarily
unavailable Backend API is optional and must not prevent local automation. Internet
unavailability remains inside the automatic 60-second retry gate. A transient
Android connection failure is retryable within the configured recovery policy.

### Startup Result

The Startup Result is the sole handoff from Session Startup to the Smart
Interaction Scheduler. It contains facts and queues, not executable startup work.

If Follower Synchronization reports one or more newly gained followers and the DM
module is enabled, the scheduler prioritizes one initial DM cycle before normal
module rotation. The DM cycle remains subject to recipient eligibility, schedule
end, daily and hourly limits, and the available DM budget. After that one cycle,
normal scheduler rotation resumes. No second follower scan is performed to build
or refresh this initial queue.

## 3. Runtime Hooks

### Purpose

Runtime Hooks are event-driven extensions to normal module execution. A hook runs
only when a module encounters its declared event. It executes inline, completes a
small bounded responsibility, and immediately returns control to the same module
and then to the Smart Interaction Scheduler.

Hooks are not startup work, modules, periodic jobs, or independent schedulers. They
never choose execution order and never preempt the scheduler.

### Hook flow

```text
Smart Scheduler selects module
  -> module executes one bounded action
  -> module emits a hook event
  -> matching Runtime Hooks run inline
  -> hook results attach to the module result
  -> module returns control
  -> Smart Scheduler makes the next decision
```

### Hook examples

#### Contact Details Scraping

```text
Follow module opens a profile
  -> contact surface is detected
  -> Contact Scraping Hook reads available details
  -> profile update is submitted to GlobalDatabaseWriter
  -> control returns to Follow
```

#### AI Replies

```text
DM module opens a conversation
  -> unread message is detected
  -> AI Reply Hook builds context and generates a validated reply
  -> reply result returns to DM
  -> control returns to the Smart Scheduler after the DM slice
```

#### Other hook categories

- tagged-account protection when a candidate is evaluated;
- statistics updates after a confirmed or failed action;
- future Save Post behavior after a qualifying Like event;
- audit enrichment after a profile, source, or action event;
- other bounded event-driven behavior added through explicit hook contracts.

### Hook rules

- A hook declares the event it handles and receives immutable event context.
- Hooks run in deterministic registration order for the same event.
- A hook must be bounded, cancellation-aware, and idempotent where it writes data.
- A hook may enrich, allow, or reject the current module action through a structured
  result, but it may not select another module or start an independent interaction.
- Hook failure is recorded with the parent module result. A failure requiring app,
  account, or device repair transfers control to Runtime Recovery.
- Hooks use the Android UI only within the module's existing serialized execution
  slice. They cannot create concurrent phone interaction.
- Hooks never wait for Global User Database writes. They submit immutable updates
  to GlobalDatabaseWriter and return immediately to the current module.
- Expensive network persistence uses a durable local record; Session Shutdown owns
  final Backend API upload rather than allowing a hook to stall module rotation.

## 4. Smart Interaction Scheduler

### Responsibility

The Smart Interaction Scheduler decides which eligible module receives the next
bounded execution slice. Modules define goals and capabilities; they do not decide
global ordering. The scheduler is the heart of a running Account Session.

It exclusively owns module rotation, interaction budgets, daily and hourly limit
enforcement, module priorities, safe randomization, scrolling decisions, and the
resulting execution order.

The scheduler replaces a fixed sequence such as running every Follow action before
every Like action.

```text
Follow slice
  -> Like slice
  -> DM slice
  -> Follow slice
  -> Unfollow slice
  -> Like slice
  -> Continue
```

Modules always rotate. The scheduler never selects the same module twice in a row
while another module is enabled, eligible, ready, and has remaining allowance. A
module may repeat only when it is the sole eligible module.

### Scheduler inputs

- enabled module set;
- module-specific session budget, configured as a fixed action count such as `15`
  or an inclusive range such as `10-20`;
- remaining daily and hourly allowance;
- account schedule end time;
- module cooldown and delay readiness;
- available sources and target queues;
- event-driven queues;
- recent failures and safety state;
- priority and weighting policy;
- current phone and application health;
- operator stop or configuration-change request.

### Module contract

Each module exposes a common conceptual contract:

- whether it is enabled and currently eligible;
- its next-ready time;
- remaining session, hourly, and daily allowance;
- whether it has an available target or event;
- a request for one bounded unit or small batch of work;
- a structured result containing attempted, confirmed, skipped, blocked, failed,
  consumed limits, cooldown, and discovered facts.

A module cannot run an unbounded source loop. It returns control after its slice so
the scheduler can rotate, observe stop requests, enforce global policy, and decide
whether the current source should continue scrolling or yield to another source or
module.

A Module Budget defines the maximum number of actions assigned to that module
before the scheduler rotates. A fixed budget uses that action count. A ranged
budget resolves one value within the inclusive range according to the session's
randomization policy and records the resolved value for auditability. A budget is
never permission to exceed a daily or hourly limit.

### Selection policy

The scheduler follows these rules in order:

1. Stop admission when the Account Session end time has arrived, even when module
   budgets remain unfinished.
2. Exclude disabled, blocked, exhausted, cooling-down, and source-empty modules.
3. Apply authoritative daily and hourly allowances before issuing work. The Daily
   Limit always overrides a larger Module Budget.
4. Prioritize one initial new-follower DM cycle when required by the Startup Result.
5. Exclude the previously selected module when another module is eligible.
6. Select from the remaining eligible modules using configured priority and safe
   randomized weighting.
7. Issue one bounded budget slice and wait for its structured result.
8. Update budgets, cooldowns, statistics, and health state.
9. Evaluate the returned module and hook results before rotating again.

Randomization changes selection among safe eligible choices. Scrolling policy
decides whether a module continues the current source, uses a configured discovery
strategy, changes source, or yields its slice. Neither randomization nor scrolling
policy may bypass limits, schedules, safety rules, or event priority.

Priority order is absolute: Account Session end time, safety and stop conditions,
daily limit, hourly limit, then Module Budget and selection policy. Unfinished
budgets are discarded at session end and never extend the configured schedule.

### Enable and disable behavior

- A disabled module is never scheduled and consumes no budget.
- Disabling a module during a stopped scheduler affects the next session.
- Execution-related configuration changes stop the Phone Scheduler according to the
  established operator policy. The operator must explicitly start it again.
- Reaching a module limit marks only that module exhausted unless a safety or
  session-level policy requires session termination.

### Compatibility execution

While InstaAddict remains the provider, a compatibility adapter translates one
IGBot work request into the narrowest supported legacy operation and translates
legacy output into a structured module result. The adapter must isolate these known
legacy characteristics:

- shared source jobs rather than independent modules;
- fixed internal Story, Like/Comment, DM, Follow order;
- per-source and per-session limits rather than true daily limits;
- configuration names that do not match operator terminology;
- file-based message and target resources;
- known defective, obsolete, or ineffective options documented by the audits.

The scheduler must never depend directly on InstaAddict argument names, YAML key
order, console text, or mutable global counters. Unsupported IGBot behavior remains
outside the adapter until a native runtime implementation exists.

## 5. Daily and Hourly Limits

### Responsibility chain

```text
Operator module goal
  -> persistent Daily Limit Ledger
  -> Smart Interaction Scheduler allowance
  -> global Hourly Limit Ledger allowance
  -> module work slice
  -> execution provider
  -> confirmed outcome
  -> atomic ledger update
```

### Limit scopes

- **Daily module limit:** per account, per module, per operator-local calendar day.
- **Hourly global limit:** shared across all running accounts as defined by the
  global policy, using rolling or fixed-hour semantics chosen once for the product.
- **Session budget:** the maximum work allocated to a module in one Account Session.
- **Module budget:** a fixed or ranged slice that controls how many actions a
  module may perform before mandatory rotation; it is bounded by all higher limits.
- **Source budget:** optional bounded work for one source so a source cannot
  monopolize a session.
- **Safety limit:** failures, crashes, blocks, and login attempts; these do not count
  as successful interaction limits.

### Accounting rules

- Limits are durable and survive application restart, phone restart, session
  failure, and provider restart.
- A confirmed Instagram outcome consumes the success limit. Attempts and failures
  are counted separately for diagnostics and retry policy.
- Reservation occurs before execution to prevent concurrent phones from exceeding a
  global allowance. The reservation is committed on confirmed success or released
  on a definite non-action.
- An ambiguous outcome is reconciled before retrying so a timeout cannot create a
  duplicate action.
- Daily reset uses the configured operator timezone and records the boundary used.
- Changing a configured limit never erases historical usage.
- The scheduler clamps every Module Budget to the remaining daily and hourly
  allowance before execution. It never issues work beyond the Daily Limit.
- Session end cancels unissued budget and takes precedence over every remaining
  allowance.

Legacy InstaAddict limits are defensive provider caps while the adapter is active.
They are not the authoritative daily ledger and must be set so they cannot permit
IGBot to exceed its own allowance.

## 6. Runtime Recovery

### Recovery model

Runtime Recovery is entered only in response to a failure. It is not part of normal
module rotation. Recovery is stateful, bounded, and observable. It resumes only
from a verified safe checkpoint and never blindly repeats an ambiguous action.

### Instagram crash

```text
detect process/UI failure
  -> mark current action interrupted
  -> capture diagnostics
  -> close stale automation resources
  -> restart Instagram
  -> wait after launch
  -> verify account and package
  -> reconcile ambiguous action outcome
  -> resume the existing session at a safe scheduler boundary
```

Restarting Instagram is mandatory runtime behavior, not an operator toggle.
Recovery does not rerun Session Startup, Follower Synchronization, or initial DM
priority. Repeated crashes consume the crash-retry limit. Exhaustion fails the
Account Session while leaving the Phone Scheduler available to evaluate later
work.

### Action block

```text
detect block signal
  -> stop issuing interaction work
  -> record affected module and action
  -> capture evidence
  -> pause only the affected account for the Global pause duration
  -> run a health recheck
  -> resume only if verified safe
```

Severe or repeated blocks may end the account session. The scheduler must not
automatically re-enable blocked modules without an explicit recovery policy.
An account paused by an action block remains unavailable to the Phone Scheduler
until the Global pause duration expires or an operator-controlled recovery
condition is satisfied. The Phone Scheduler remains alive and continues scheduling
other eligible accounts on that phone. Other phones and accounts are unaffected.

### Login failure or challenge

```text
verify login state
  -> retry according to Login Retry Limit
  -> increment daily login retry ledger
  -> enter WAITING_FOR_OPERATOR after the limit is exhausted
  -> notify operator and synchronize account state
```

Credentials and challenge state are never written to logs. A paused account is
skipped by the Phone Scheduler until the operator resolves it or policy permits a
new attempt. `WAITING_FOR_OPERATOR` belongs to the affected account only; the Phone
Scheduler continues evaluating and running other eligible accounts.

### Device and automation failures

- ADB disconnect pauses the phone scheduler and waits for reconnection within a
  bounded window.
- Unauthorized devices require operator action and cannot be retried as ordinary
  connection failures.
- Automation-bridge failure triggers bridge recovery, then application recovery if
  necessary.
- Phone loss never causes another connected phone to inherit the session.
- Every cleanup restores only device state IGBot changed and records incomplete
  restoration for operator review.

## 7. Session Shutdown

Session Shutdown is the final Account Session stage. It executes once after normal
completion, schedule end, operator cancellation, or unrecoverable failure. Each
step is best-effort during a damaged session, but failures are retained in the
final result rather than silently ignored.

### Shutdown order

1. **Stop new work.** Close scheduler admission and reject new module slices and
   Runtime Hook invocations.
2. **Settle current work.** Complete or cancel the current safe action boundary and
   reconcile ambiguous outcomes.
3. **Finalize limits and statistics.** Commit confirmed reservations, release
   unused reservations, aggregate module and hook results, and record the terminal
   session status.
4. **Persist runtime state.** Enqueue durable session history, source performance,
   follower snapshots, pending event queues, recovery outcomes, and the next safe
   resume state. Shutdown does not wait for physical database writes.
5. **Create synchronization records.** Write durable Backend API outbox entries for
   statistics, analytics, health, contacts, and session completion.
6. **Upload Backend API data.** Attempt a bounded outbox flush. Failure leaves
   records durable for a later retry and does not corrupt local completion.
7. **Close Instagram.** Stop the assigned package when session policy requires it
   and release automation resources.
8. **Restore owned device state.** Restore temporary keyboard, notification,
   network, and automation state changed by this session where applicable.
9. **Release phone ownership.** Return a complete terminal result to the Phone
   Scheduler.
10. **Prepare the next account.** The Phone Scheduler reloads eligible schedules
    and selects the next account or enters `Waiting`.

Session Shutdown never chooses the next module and never launches another account
itself. It finalizes exactly one Account Session and hands control back to the Phone
Scheduler.

## 8. Contact Scraping

### Workflow

Contact scraping is one global operator feature, not separate Email, Phone, and
Website modules. During a session it runs as a Runtime Hook triggered by an already
open profile.

```text
eligible profile encountered
  -> capture profile identity and visible profile data
  -> inspect available business/contact surfaces when enabled
  -> normalize contact fields
  -> submit shared profile facts to GlobalDatabaseWriter
  -> record source and interaction provenance in the Per-Account Runtime Database
  -> enqueue synchronization event
```

### Data model

Where available, the shared profile record may contain:

- Instagram username;
- full name;
- biography;
- follower, following, and post counts;
- private, verified, and business flags;
- email addresses;
- phone numbers;
- websites and other public links;
- other available business contact information;
- last-updated timestamp.

Missing data is not represented as a negative fact. Every value retains provenance
inside the write request so later observations can update stale details safely. The
Global User Database stores the resulting profile facts only; observing account,
module, source, session, and interaction history belong exclusively to the
Per-Account Runtime Database and audit stream.

### Runtime rules

- Scraping occurs inline while a module already has the relevant profile open,
  avoiding duplicate navigation and returning control immediately afterward.
- The hook uses the module's serialized phone interaction slot and cannot start a
  second navigation flow.
- The hook submits an immutable update and does not wait for database persistence.
- GlobalDatabaseWriter makes Global User Database writes idempotent, batched, and
  asynchronous.
- Sensitive data handling, retention, lawful use, and backend access are governed
  outside module configuration and must be applied consistently.

## 9. AI Runtime

AI is a future content-decision service behind a provider-neutral boundary. Modules
request content; they do not call a model provider directly.

### Architecture

```text
DM / Comment / Reply event
  -> AI policy and eligibility gate
  -> context builder
  -> prompt-template resolver
  -> model provider adapter
  -> structured response validation
  -> safety and duplication checks
  -> module delivery queue
  -> send and record outcome
```

### Context

Context may include only explicitly permitted information such as the operator's
prompt, target profile data, relevant source, recent interaction history, account
voice/template, and bounded conversation context for replies. Credentials, API
secrets, unrelated accounts, and unrestricted local files are never model context.

### Responsibilities

- The global AI configuration owns provider, model, API credential reference, and
  generation parameters.
- Prompt templates own reusable operator intent.
- Account configuration owns account-specific selections without embedding secrets.
- The AI service validates structured output, length, required variables, and
  policy before returning content.
- DM, Comment, and Reply modules remain responsible for recipient eligibility,
  limits, delivery, confirmation, and history.
- Generated content and model metadata are auditable without logging API secrets or
  unnecessary private context.

AI failure defers or rejects the related event according to policy. It never blocks
unrelated enabled modules or silently falls back to unintended content.

AI Replies execute as Runtime Hooks when a conversation event is encountered. AI
DM and Comment generation remain services invoked by their owning modules. AI
never owns scheduling or starts an independent phone interaction.

## 10. Website Synchronization

### Boundary

All remote communication uses one Backend API integration. Runtime components emit
domain events to a local durable outbox; they do not make arbitrary network calls.

### Outbound data

- phone scheduler and account-session status;
- session start, completion, failure, and cancellation;
- confirmed module statistics and limit consumption;
- source performance and Follow Back Ratio results;
- analytics snapshots;
- contact records permitted for synchronization;
- account health, blocks, login state, and operator-attention events.

### Inbound data

Future inbound synchronization may supply newly created client accounts, approved
configuration revisions, control requests, or account-state updates. Every inbound
change is authenticated, validated, versioned, and applied through the same local
services used by the desktop application.

Remote changes never mutate a running account session in place. Execution-related
changes stop the affected Phone Scheduler, persist the new revision, and require an
explicit restart under the established operator policy.

### Reliability

- Outbox entries are idempotent, ordered per entity, and retried with backoff.
- Local runtime continues when the backend is unavailable.
- Acknowledged records are retained according to audit and retention policy.
- Conflicts use explicit configuration revisions; last-write-wins is not assumed.
- API credentials are stored through a secrets boundary and never in logs or
  account engine configuration.
- Synchronization cannot command Android UI work outside a Phone Scheduler.

## 11. Database Architecture

Runtime knowledge is divided between two independent databases. They have
different ownership, retention, and query responsibilities and must never be
collapsed into a single interaction record.

### Global User Database

The Global User Database is a shared profile knowledge base used across all IGBot
accounts and phones. It contains only the latest known profile information:

- username;
- full name;
- biography;
- followers;
- following;
- posts;
- private;
- verified;
- business;
- email;
- phone;
- website;
- last updated.

It contains no account interaction history, module results, source relationships,
session identifiers, followed state, DM state, or account-specific decisions. A
profile observed by many IGBot accounts remains one shared profile entity.

### Per-Account Runtime Database

Each managed Instagram account owns an independent Runtime Database. It describes
only what that IGBot account did or learned through its own runtime activity. A
record may contain:

- `followed` and `follow_date`;
- `unfollowed` and `unfollow_date`;
- `follow_back` and `follow_back_date`;
- `dm_sent` and `dm_date`;
- `discovered_by`;
- `source_account`;
- `session_id`.

Per-account data is never promoted to the Global User Database as interaction
history. Shared profile facts discovered during an interaction are submitted
separately to GlobalDatabaseWriter. Account transfer or archive changes assignment
and availability; it does not merge one account's Runtime Database into another.

### GlobalDatabaseWriter

GlobalDatabaseWriter is the only component permitted to write to the Global User
Database. Runtime sessions, modules, hooks, recovery, UI, synchronization, and
compatibility adapters never write to that database directly.

Its responsibilities are:

- receive immutable profile updates from concurrent runtime instances;
- validate and normalize profile fields without adding interaction history;
- coalesce repeated observations and batch database writes;
- persist asynchronously through a bounded, durable queue;
- apply idempotent updates and preserve the newest valid observation;
- publish persistence success or failure for audit and retry handling.

Submitting a profile update must be fast and non-blocking for phone automation. A
temporary database failure retains or retries queued updates according to storage
policy; it never stalls Android interaction. Backpressure is observable and uses a
durable fallback rather than blocking a phone session.

Per-Account Runtime Database changes also pass through asynchronous persistence
owned by that account's runtime state boundary. Ordering is preserved per account,
but the current Android action and Smart Interaction Scheduler never wait for a
physical database write.

## 12. Runtime Components and Boundaries

### Fleet Runtime

Owns the registry of Phone Schedulers, global hourly allowances, fleet Start/Stop,
and application shutdown coordination. It never performs account interactions.

### Phone Scheduler

Owns one phone, loads assigned accounts, interprets account schedules, selects the
next eligible account, guarantees single-session phone ownership, and remains alive
while waiting. It does not implement module behavior.

### RuntimeContext

Owns the references and mutable state for exactly one Account Session, including
its immutable session identity, RuntimeLogger, runtime settings, session state,
Startup Result, and future scheduler state. Every session component receives this
same context. RuntimeContext is not a service locator and never owns business
logic.

### RuntimeLogger

Defines the only logging interface used by the native runtime. It emits
provider-independent debug, information, warning, and error messages with optional
structured fields. Destination adapters, persistence, UI delivery, and Backend API
delivery remain outside runtime components.

### InternetChecker

Owns only the first Session Startup connectivity gate. It polls NetworkProvider,
logs the fixed 60-second retry message through RuntimeLogger, waits between
unavailable observations, and returns a structured startup-stage result after
connectivity is restored or the provider itself fails.

### NetworkProvider

Defines the platform-independent Internet availability observation consumed by
InternetChecker. AndroidNetworkProvider implements this boundary using an isolated
ADB reachability probe. Future platforms may replace that provider without
changing InternetChecker, StartupPipeline, or SessionController.

### Account Session

Owns one bounded run for one account: Session Startup, serialized phone access,
Smart Interaction Scheduler, inline Runtime Hooks, Runtime Recovery, cancellation,
and Session Shutdown.

### Smart Interaction Scheduler

Owns module eligibility, rotation, budgets, daily and hourly limit decisions,
priorities, cooldowns, safe randomization, scrolling decisions, and execution order.
It does not manipulate Android directly.

### Modules

Follow, Unfollow, Like, Story, Comment, and DM own their domain-specific candidate
requirements, action request, and structured result interpretation. They do not own
phone selection, session lifecycle, global limits, or other modules.

### Runtime Hook Dispatcher

Matches module events to bounded inline hooks, preserves deterministic hook order,
collects structured outcomes, and returns control to the parent module. It does not
schedule modules or own independent phone work.

### GlobalDatabaseWriter

Receives profile observations from every runtime instance, batches and persists
them asynchronously, and is the exclusive writer to the Global User Database. It
does not own interaction history or perform Android work.

### Limit Ledger

Atomically reserves, commits, releases, resets, and reports daily, hourly, session,
source, retry, and safety allowances.

### Recovery Coordinator

Classifies failures, captures diagnostics, executes bounded recovery plans, and
returns a verified result to the Account Session.

### Session Shutdown Coordinator

Finalizes limits and statistics, persists terminal state, creates and flushes
Backend API outbox records, closes Instagram, restores owned device state, and
returns phone ownership to the Phone Scheduler.

### Execution Provider

Provides the narrow Android or automation operation requested by a module. The
InstaAddict adapter is one provider. Future native IGBot providers implement the
same conceptual operation/result boundary.

### Event and Audit Pipeline

Distributes immutable lifecycle, action, error, statistics, and synchronization
events. Live Log is one consumer. It is not the runtime data store.

## 13. Runtime Principles

1. **The phone is the execution unit.** One persistent scheduler owns each started
   phone; one account runs on that phone at a time.
2. **Runtime owns behavior.** UI pages edit intent and display state; they do not
   schedule work or manipulate engine processes.
3. **Session Startup runs once.** It prepares the network, application, account,
   health, one Follower Synchronization scan, and the Startup Result before any
   module runs.
4. **Modules define goals.** They expose eligibility and bounded work; they do not
   control the session or each other.
5. **The Smart Interaction Scheduler owns execution order.** Rotation, priorities,
   budgets, daily and hourly limits, cooldowns, randomization, and scrolling
   decisions are centralized.
6. **Runtime Hooks respond inline.** They handle events encountered during module
   execution and immediately return control. They never interrupt or replace the
   scheduler.
7. **Runtime Recovery handles failures only.** Restart, retry, pause, and resume
   occur through bounded recovery plans and verified checkpoints.
8. **Session Shutdown finalizes once.** It persists state and statistics, creates
   and flushes synchronization records, closes resources, and returns the phone to
   its scheduler.
9. **Limits are authoritative and durable.** Provider counters are defensive
   compatibility mechanisms, not IGBot's daily or hourly truth.
10. **Confirmed outcomes drive accounting.** Attempts, ambiguous results, failures,
   and successes remain distinct.
11. **Configuration is snapshotted.** A session runs one validated revision.
   Execution-related changes stop the scheduler rather than mutating a live run.
12. **Compatibility is isolated.** The InstaAddict adapter translates IGBot
    behavior into current InstaAddict operations, terminology, files, limits, and
    results without exposing legacy details to the UI or scheduler.
13. **Known legacy defects are not product behavior.** Obsolete keys, ineffective
    options, parser quirks, and fixed action order remain contained in the adapter.
14. **Local operation is resilient.** Backend and AI outages do not corrupt local
    state or stop unrelated modules and phones.
15. **Every action is observable.** State transitions, scheduling decisions,
    recovery, limit consumption, and synchronization outcomes are structured and
    auditable.
16. **Secrets remain outside logs and engine configuration.** Credentials and API
    keys cross only explicit protected boundaries.
17. **Operator terminology is authoritative.** The UI and runtime model reflect the
    operator workflow; engine vocabulary is an internal translation detail.
18. **Automation never waits for database writes.** Runtime components submit
    immutable updates to asynchronous persistence boundaries and continue Android
    work without waiting for physical writes.
19. **Phone automation has priority over persistence.** Queueing, batching,
    backpressure, retry, and durable fallback belong to database writers and cannot
    take ownership of the phone interaction channel.
20. **The Global User Database has one writer.** GlobalDatabaseWriter is the only
    component allowed to persist shared profile facts; runtime instances never
    write to it directly.
21. **Profile facts and interaction history remain separate.** Shared profile data
    belongs to the Global User Database. Follow, Unfollow, DM, source, and session
    facts belong to the relevant Per-Account Runtime Database.
22. **RuntimeContext is session-scoped.** One context is created by
    SessionController and shared by startup, scheduling, modules, hooks, recovery,
    compatibility, and shutdown for that Account Session only.
23. **Runtime components never own global state.** Account, phone, settings,
    logger, Startup Result, and evolving runtime state are accessed through the
    supplied RuntimeContext rather than globals or parallel parameter lists.
24. **RuntimeLogger is the sole runtime logging interface.** Runtime components do
    not print directly, select destinations, write log files, or call UI logging
    facilities.
25. **Every component has one responsibility.** Context sharing does not permit a
    stage, module, hook, recovery strategy, adapter, or logger to assume another
    subsystem's ownership.

### Execution-stage summary

```text
Session Startup
  -> runs exactly once
Smart Interaction Scheduler
  -> owns execution order and limits
Runtime Hooks
  -> respond inline to events encountered by modules
Runtime Recovery
  -> runs only when failures occur
Session Shutdown
  -> finalizes exactly once
Compatibility Layer
  -> translates IGBot behavior into the current InstaAddict engine
```

## 14. Reference Session

```text
Phone Scheduler selects Account A
  -> Session Startup runs once
       -> wait for Internet, retrying every 60 seconds while unavailable
       -> optionally toggle Airplane Mode and wait for the mobile network
       -> launch Instagram and wait after launch
       -> verify Account A and its Application ID
       -> run one Follower Synchronization scan
            -> update FBR
            -> detect newly gained followers
       -> build Startup Result and fixed or ranged module budgets
  -> Smart Interaction Scheduler starts
  -> run one prioritized DM cycle when Startup Result contains new followers
  -> run Follow slice
       -> Contact Details Hook runs when contact details are encountered
       -> submit profile facts to GlobalDatabaseWriter without waiting
       -> control returns to Follow
  -> run Like slice
       -> Statistics Hook records the confirmed action
       -> control returns to Like
  -> run DM slice for eligible new-follower work
       -> AI Reply Hook runs only if an unread-message event is encountered
       -> control returns to DM
  -> run Story slice
  -> run Follow slice
  -> Instagram crashes
       -> Runtime Recovery restarts Instagram and verifies Account A
       -> Session Startup does not run again
       -> control returns at a safe Smart Scheduler boundary
  -> stop at Account A's schedule end
  -> Session Shutdown runs once
       -> persist final statistics, limits, and runtime state
       -> create and upload Backend API records
       -> close Instagram and restore owned device state
  -> return phone ownership to Phone Scheduler
  -> select Account B or wait for the next schedule
```

This lifecycle is the target behavior even while individual operations are served
through the InstaAddict compatibility adapter. Future native IGBot execution can
replace the adapter without changing the operator workflow, scheduler contracts,
limit accounting, state model, or UI.
