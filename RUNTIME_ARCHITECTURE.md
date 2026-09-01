# IGBot Runtime Architecture

## Status and Purpose

This document is the master specification for the future IGBot runtime. It defines
the intended operator-facing behavior independently of InstaAddict's current
execution model. It is an architecture specification, not an implementation plan
or a description of completed runtime functionality.

The IGBot runtime owns scheduling, limits, recovery, background work, state,
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
            -> Startup Background Tasks
            -> Smart Interaction Scheduler
                 -> interaction modules
                 -> periodic background tasks
            -> Session Finalization
            -> statistics and synchronization
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
  -> run startup background tasks
  -> build module budgets and event queues
  -> run Smart Interaction Scheduler
  -> interleave modules and due background tasks
  -> stop at schedule end, operator request, safety stop, or completed session
  -> finalize state and statistics
  -> enqueue backend synchronization
  -> return control to Phone Scheduler
  -> select another eligible account or wait
```

### Runtime state ownership

The runtime exposes explicit states rather than inferring state from processes or
buttons.

- Phone Scheduler: `Stopped`, `Starting`, `Waiting`, `Running`, `Stopping`, `Error`.
- Account Session: `Pending`, `Starting`, `Running`, `Paused`, `Recovering`,
  `Stopping`, `Completed`, `Failed`, `Cancelled`.
- Module: `Disabled`, `Ready`, `Running`, `CoolingDown`, `LimitReached`, `Blocked`,
  `Failed`.
- Background task: `Pending`, `Running`, `Deferred`, `Completed`, `Failed`.

State changes are published as events to the UI, audit log, statistics store, and
future synchronization layer. The UI displays runtime state but does not calculate
or own it.

### Stop semantics

Stop is cooperative and phone-scoped:

1. Reject new module and background-task work.
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

1. **Acquire phone ownership.** Confirm that no other Account Session owns the
   phone's Android interaction channel.
2. **Reload authoritative configuration.** Read account identity, device
   assignment, Application ID, schedule, enabled modules, limits, and global
   settings from their designated stores.
3. **Validate identity and assignment.** Confirm that the account is active,
   belongs to this phone, is not archived, and has one unambiguous configuration.
4. **Validate the phone.** Confirm ADB connectivity and authorization and verify
   that the selected phone still matches the stable Android serial.
5. **Validate the application.** Require a valid Application ID and confirm that
   the package is installed and launchable.
6. **Apply optional network preparation.** If enabled, toggle Airplane Mode and
   wait for mobile connectivity to return before opening Instagram.
7. **Prepare device services.** Establish the Android automation connection,
   normalize temporary input state, and run mandatory health checks.
8. **Launch Instagram.** Open the assigned package and wait for the configured
   launch delay.
9. **Verify the selected Instagram account.** Confirm that the visible account
   matches the session account. Attempt bounded account selection when necessary.
10. **Verify session health.** Detect login challenges, unavailable UI, action
    blocks, incompatible application state, and repeated startup crashes.
11. **Create the session snapshot.** Record start time, configuration revision,
    phone, account, enabled modules, schedules, and limit balances.
12. **Run startup background tasks.** Execute the required tasks below before
    interaction rotation begins.
13. **Build scheduler inputs.** Create module budgets, cooldown state, event queues,
    and the first scheduling decision.

### Startup background-task order

1. Follow Back Ratio check, when enabled and meaningful for the configured sources.
2. New-follower scan and comparison with the interaction database.
3. DM queue creation for eligible newly gained followers.
4. Inbox scan when reply processing is enabled in a future runtime.
5. Contact and profile-data refresh required by session policy.
6. Initial analytics snapshot.
7. Backend inbound synchronization and account-state reconciliation.

Failures are classified as fatal, retryable, or optional. A missing Application ID
or wrong account is fatal. A temporarily unavailable backend is optional and must
not prevent local automation. A transient Android connection failure is retryable
within the configured recovery policy.

## 3. Background Tasks

### Purpose

Background tasks perform session support work that is not a normal interaction
module. They produce facts, queues, or synchronization records; they do not compete
for module budgets.

### Task categories

| Task | Purpose | Typical timing | Scheduler interaction |
|---|---|---|---|
| Follow Back Ratio | Compare source-originated follows with resulting followers and update source performance | Session startup; optionally once per session | Completes before follower-source scoring is used |
| New-follower detection | Compare the current follower snapshot with the previous durable snapshot | Startup and configured periodic interval | Produces a new-follower event queue |
| Inbox checking | Detect unread or reply-eligible conversations | Startup and periodic interval | Produces reply events; does not behave as a source module |
| Contact scraping | Collect permitted public/business contact details from profiles already visited | Inline capture or a bounded queued task | Uses the phone UI only when granted an execution slot |
| Analytics update | Aggregate action results, limits, failures, profile counts, and source performance | Incrementally and at finalization | Updates scheduler facts without blocking ordinary rotation |
| Backend synchronization | Upload outbox records and retrieve permitted remote changes | Startup, periodic, finalization | Network-only work may run concurrently; UI work may not |
| Runtime health check | Verify ADB, automation bridge, foreground app, and account state | Startup and between module slices | May pause scheduling and start recovery |

### Coordination rules

- A phone has one serialized Android interaction channel. A task that touches the
  Instagram UI must acquire it through the Account Session.
- Network-only and local aggregation work may run concurrently when it cannot
  mutate session decisions unsafely.
- Every task has a deadline, retry policy, cancellation token, and idempotency key.
- Periodic tasks declare their next due time. The Smart Interaction Scheduler checks
  due tasks between module slices, never in the middle of an unsafe Android action.
- Task failure is logged and classified. Optional task failure does not terminate
  the session; health or identity failures may pause or stop it.
- Task results are durable facts. Modules consume those facts through typed queues
  or read-only state, not by reaching into another task's internal data.

### Event-driven work

New-follower DMs and future replies are event-driven actions:

```text
Follower snapshot
  -> detect newly gained follower
  -> verify history and eligibility
  -> create durable DM event
  -> DM module receives event budget
  -> send or defer
  -> record terminal outcome
```

An event remains pending, completed, rejected, or failed. It is not silently lost
when a session ends or a send attempt fails.

## 4. Smart Interaction Scheduler

### Responsibility

The Smart Interaction Scheduler decides which eligible module receives the next
bounded execution slice. Modules define goals and capabilities; they do not decide
global ordering.

The scheduler replaces a fixed sequence such as running every Follow action before
every Like action.

```text
Follow slice
  -> Like slice
  -> Follow slice
  -> DM event
  -> Story slice
  -> due background task
  -> Like slice
```

### Scheduler inputs

- enabled module set;
- module-specific session budget;
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
the scheduler can rotate, process due background tasks, observe stop requests, and
enforce global policy.

### Selection policy

The scheduler follows these rules in order:

1. Exclude disabled, blocked, exhausted, cooling-down, and source-empty modules.
2. Reserve capacity for due event-driven work and urgent health tasks.
3. Apply daily and hourly allowances before issuing work.
4. Avoid immediately repeating the same module when another eligible module exists.
5. Select from eligible modules using configured priority and randomized weighting.
6. Issue a bounded slice and wait for its structured result.
7. Update budgets, cooldowns, statistics, and health state.
8. Run any newly due background task before the next selection.

Randomization changes selection among safe eligible choices. It never bypasses
limits, schedules, safety rules, or event priority.

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

Legacy InstaAddict limits are defensive provider caps while the adapter is active.
They are not the authoritative daily ledger and must be set so they cannot permit
IGBot to exceed its own allowance.

## 6. Runtime Recovery

### Recovery model

Recovery is stateful, bounded, and observable. It resumes only from a verified safe
checkpoint; it never blindly repeats an ambiguous action.

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
  -> resume scheduler at a safe boundary
```

Restarting Instagram is mandatory runtime behavior, not an operator toggle.
Repeated crashes consume the crash-retry limit. Exhaustion fails the Account
Session while leaving the Phone Scheduler available to evaluate later work.

### Action block

```text
detect block signal
  -> stop issuing interaction work
  -> record affected module and action
  -> capture evidence
  -> apply configured pause/cooldown
  -> run a health recheck
  -> resume only if verified safe
```

Severe or repeated blocks may end the account session. The scheduler must not
automatically re-enable blocked modules without an explicit recovery policy.

### Login failure or challenge

```text
verify login state
  -> retry bounded account selection/login recovery
  -> increment daily login retry ledger
  -> pause account after limit
  -> notify operator and synchronize account state
```

Credentials and challenge state are never written to logs. A paused account is
skipped by the Phone Scheduler until the operator resolves it or policy permits a
new attempt.

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

## 7. Contact Scraping

### Workflow

Contact scraping is one global operator feature, not separate Email, Phone, and
Website modules.

```text
eligible profile encountered
  -> capture profile identity and visible profile data
  -> inspect available business/contact surfaces when enabled
  -> normalize contact fields
  -> attach source, account, and observation timestamp
  -> upsert local contact record
  -> enqueue synchronization event
```

### Data model

Where available, a contact record may contain:

- Instagram username and stable observed profile identifier;
- display name;
- biography;
- email addresses;
- phone numbers;
- websites and other public links;
- visible business category and other available business contact information;
- source module and source target;
- observing IGBot account and phone;
- first-seen and last-seen timestamps;
- validation and provenance for every field.

Missing data is not represented as a negative fact. Every value retains provenance
so later observations can update stale details without losing history.

### Runtime rules

- Scraping is opportunistic during profiles already opened by modules whenever
  possible, avoiding duplicate navigation.
- A dedicated queued scrape may run only through the serialized phone interaction
  channel.
- Database writes are idempotent and do not block Android interaction longer than
  necessary.
- Sensitive data handling, retention, lawful use, and backend access are governed
  outside module configuration and must be applied consistently.

## 8. AI Runtime

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

## 9. Website Synchronization

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

## 10. Runtime Components and Boundaries

### Fleet Runtime

Owns the registry of Phone Schedulers, global hourly allowances, fleet Start/Stop,
and application shutdown coordination. It never performs account interactions.

### Phone Scheduler

Owns one phone, loads assigned accounts, interprets account schedules, selects the
next eligible account, guarantees single-session phone ownership, and remains alive
while waiting. It does not implement module behavior.

### Account Session

Owns one bounded run for one account: startup, serialized phone access, background
tasks, Smart Interaction Scheduler, recovery, cancellation, and finalization.

### Smart Interaction Scheduler

Owns module eligibility, rotation, budgets, priorities, cooldowns, and due-task
interleaving. It does not manipulate Android directly.

### Modules

Follow, Unfollow, Like, Story, Comment, and DM own their domain-specific candidate
requirements, action request, and structured result interpretation. They do not own
phone selection, session lifecycle, global limits, or other modules.

### Background Task Coordinator

Owns startup, periodic, and event-producing support tasks and coordinates safe phone
access with the Account Session.

### Limit Ledger

Atomically reserves, commits, releases, resets, and reports daily, hourly, session,
source, retry, and safety allowances.

### Recovery Coordinator

Classifies failures, captures diagnostics, executes bounded recovery plans, and
returns a verified result to the Account Session.

### Execution Provider

Provides the narrow Android or automation operation requested by a module. The
InstaAddict adapter is one provider. Future native IGBot providers implement the
same conceptual operation/result boundary.

### Event and Audit Pipeline

Distributes immutable lifecycle, action, error, statistics, and synchronization
events. Live Log is one consumer. It is not the runtime data store.

## 11. Runtime Principles

1. **The phone is the execution unit.** One persistent scheduler owns each started
   phone; one account runs on that phone at a time.
2. **Runtime owns behavior.** UI pages edit intent and display state; they do not
   schedule work or manipulate engine processes.
3. **Modules define goals.** They expose eligibility and bounded work; they do not
   control the session or each other.
4. **The scheduler makes decisions.** Rotation, priorities, budgets, cooldowns, and
   due background tasks are centralized.
5. **Background tasks are independent.** They produce facts and events and use the
   phone only through coordinated execution slots.
6. **Limits are authoritative and durable.** Provider counters are defensive
   compatibility mechanisms, not IGBot's daily or hourly truth.
7. **Confirmed outcomes drive accounting.** Attempts, ambiguous results, failures,
   and successes remain distinct.
8. **Recovery is automatic but bounded.** Restart, retry, pause, and resume require
   verified checkpoints and auditable reasons.
9. **Configuration is snapshotted.** A session runs one validated revision.
   Execution-related changes stop the scheduler rather than mutating a live run.
10. **Compatibility is isolated.** The InstaAddict adapter translates terminology,
    files, limits, and results without exposing legacy implementation details to the
    UI or scheduler.
11. **Known legacy defects are not product behavior.** Obsolete keys, ineffective
    options, parser quirks, and fixed action order remain contained in the adapter.
12. **Local operation is resilient.** Backend and AI outages do not corrupt local
    state or stop unrelated modules and phones.
13. **Every action is observable.** State transitions, scheduling decisions,
    recovery, limit consumption, and synchronization outcomes are structured and
    auditable.
14. **Secrets remain outside logs and engine configuration.** Credentials and API
    keys cross only explicit protected boundaries.
15. **Operator terminology is authoritative.** The UI and runtime model reflect the
    operator workflow; engine vocabulary is an internal translation detail.

## 12. Reference Session

```text
Phone Scheduler selects Account A
  -> validate phone, account, package, schedule, and configuration
  -> optionally refresh mobile IP
  -> launch Instagram and verify Account A
  -> run health checks
  -> calculate FBR
  -> detect new followers and create DM events
  -> capture initial analytics
  -> construct Follow, Like, Story, Comment, Unfollow, and DM budgets
  -> run Follow slice
  -> run Like slice
  -> process one new-follower DM event
  -> run Story slice
  -> execute due health and follower checks
  -> run Follow slice
  -> recover from an Instagram crash and verify state
  -> continue from a safe scheduler boundary
  -> stop at Account A's schedule end
  -> persist final statistics and limit usage
  -> enqueue backend synchronization
  -> return phone ownership to Phone Scheduler
  -> select Account B or wait for the next schedule
```

This lifecycle is the target behavior even while individual operations are served
through the InstaAddict compatibility adapter. Future native IGBot execution can
replace the adapter without changing the operator workflow, scheduler contracts,
limit accounting, state model, or UI.
