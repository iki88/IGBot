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
- Module: `Disabled`, `Ready`, `Running`, `CoolingDown`, `LimitReached`, `Blocked`,
  `Failed`.
- Runtime Hook invocation: `Triggered`, `Running`, `Completed`, `Failed`.

State changes are published as events to the UI, audit log, statistics store, and
future synchronization layer. The UI displays runtime state but does not calculate
or own it.

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
12. **Run Follow Back Ratio.** When enabled and meaningful for the configured
    sources, compare prior source interactions with the current follower state and
    update source performance facts.
13. **Run the initial new-follower scan.** Compare the current follower snapshot
    with the previous durable snapshot and prepare any eligible new-follower DM
    work for the DM module.
14. **Initialize runtime state.** Record the initial analytics snapshot and prepare
    the session's interaction history, health state, and scheduler inputs.
15. **Build scheduler inputs.** Create module budgets, cooldown state, target queues,
    and the first scheduling decision.

Every item in Session Startup executes exactly once for that Account Session. FBR,
the initial new-follower scan, account verification, launch work, and runtime
initialization are startup stages, not Runtime Hooks and not scheduler modules.

Failures are classified as fatal, retryable, or optional. A missing Application ID
or wrong account is fatal. A temporarily unavailable backend is optional and must
not prevent local automation. A transient Android connection failure is retryable
within the configured recovery policy.

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
  -> contact record is updated
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
  -> Follow slice
  -> DM event
  -> Like slice
  -> Continue
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
the scheduler can rotate, observe stop requests, enforce global policy, and decide
whether the current source should continue scrolling or yield to another source or
module.

### Selection policy

The scheduler follows these rules in order:

1. Exclude disabled, blocked, exhausted, cooling-down, and source-empty modules.
2. Reserve capacity for eligible event-driven module work.
3. Apply daily and hourly allowances before issuing work.
4. Avoid immediately repeating the same module when another eligible module exists.
5. Select from eligible modules using configured priority and randomized weighting.
6. Issue a bounded slice and wait for its structured result.
7. Update budgets, cooldowns, statistics, and health state.
8. Evaluate the returned module and hook results before the next selection.

Randomization changes selection among safe eligible choices. Scrolling policy
decides whether a module continues the current source, uses a configured discovery
strategy, changes source, or yields its slice. Neither randomization nor scrolling
policy may bypass limits, schedules, safety rules, or event priority.

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
An account paused by an action block remains unavailable to the Phone Scheduler
until its cooldown or operator-controlled recovery condition is satisfied.

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
4. **Persist runtime state.** Save session history, source performance, follower
   snapshots, pending event queues, recovery outcomes, and the next safe resume
   state.
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

- Scraping occurs inline while a module already has the relevant profile open,
  avoiding duplicate navigation and returning control immediately afterward.
- The hook uses the module's serialized phone interaction slot and cannot start a
  second navigation flow.
- Database writes are idempotent and do not block Android interaction longer than
  necessary.
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

## 11. Runtime Components and Boundaries

### Fleet Runtime

Owns the registry of Phone Schedulers, global hourly allowances, fleet Start/Stop,
and application shutdown coordination. It never performs account interactions.

### Phone Scheduler

Owns one phone, loads assigned accounts, interprets account schedules, selects the
next eligible account, guarantees single-session phone ownership, and remains alive
while waiting. It does not implement module behavior.

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

## 12. Runtime Principles

1. **The phone is the execution unit.** One persistent scheduler owns each started
   phone; one account runs on that phone at a time.
2. **Runtime owns behavior.** UI pages edit intent and display state; they do not
   schedule work or manipulate engine processes.
3. **Session Startup runs once.** It prepares the network, application, account,
   health, FBR, initial follower state, and scheduler inputs before any module runs.
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

## 13. Reference Session

```text
Phone Scheduler selects Account A
  -> Session Startup runs once
       -> validate phone, account, package, schedule, and configuration
       -> optionally refresh mobile IP and wait for network
       -> launch Instagram and wait after launch
       -> verify Account A and Application ID
       -> initialize runtime state
       -> calculate FBR
       -> perform initial new-follower scan
       -> construct Follow, Like, Story, Comment, Unfollow, and DM budgets
  -> Smart Interaction Scheduler starts
  -> run Follow slice
       -> Contact Details Hook runs when contact details are encountered
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
