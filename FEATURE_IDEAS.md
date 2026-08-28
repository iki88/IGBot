# IGBot Feature Ideas

This document is the long-term backlog for ideas intentionally outside IGBot Version 1. Keep entries concise and organize future additions under the appropriate section.

## AI

- AI Comments
- AI Direct Messages
- AI Replies
- AI Prompt Library
- AI Prompt Templates
- Vision-based post analysis
- Future video analysis
- AI profile analysis
- AI target scoring

## Analytics

- Daily analytics
- Followers graph
- Following graph
- Session history
- Module statistics
- Success rates
- Charts
- Reports

## Database

- MongoDB synchronization
- Website synchronization
- API upload
- Dashboard integration

## Scheduler

Future scheduler improvements will be collected here.

## Automation

- Automatic Follow Increase
- Optional Visit Target Profile behavior
- Optional Scroll Profile behavior
- Optional Like Random Posts behavior
- Save Posts — Future IGBot Runtime Extension allowing operators to enable automatic saving of liked posts with a configurable chance, such as `Save Posts` and `Chance to Save Posts: 1%`.
- Replace the free-text Allowed Alphabets editor with a checklist for Latin, Cyrillic, Arabic, Greek, Hebrew, and Chinese/Japanese/Korean.

## User Experience

Future workflow improvements will be collected here.

## Administration

Future operator tools will be collected here.

# Smart Interaction Scheduler

## Purpose

Move beyond the current sequential InstaAddict interaction pipeline and replace it
with an intelligent module-based session scheduler designed around real operator
workflows.

## Design Goals

The Phone Scheduler continues selecting which account runs.

Inside a running account session, a new Smart Interaction Scheduler controls which
modules execute and in what order.

## Architecture

```text
Phone Scheduler
  ↓
Account Session
  ↓
Session Initialization
  ↓
Smart Interaction Scheduler
  ↓
Modules
  ↓
Session End
```

## Session Initialization

The following tasks should always execute before interaction modules:

- Open the assigned account.
- Perform Follow-Back Ratio (FBR) calculation.
- Scan newly gained followers.
- Compare new followers with the interaction database.
- Build an optional DM queue for newly gained followers.
- Perform future startup health checks.

These are startup tasks, not interaction modules.

## Interaction Scheduler

Instead of executing one fixed sequence, the scheduler owns all enabled modules.

Examples:

- Follow
- Unfollow
- Like
- Story
- DM
- Comment

Each module receives its own configurable session budget.

Example:

- Follow: 15 follows
- Like: 40 likes
- Story: 25 story views

The scheduler rotates naturally between enabled modules.

Example session:

```text
Follow
  ↓
Like
  ↓
Follow
  ↓
Story
  ↓
Like
  ↓
Follow
```

This replaces processing every Follow action first.

## Module Rotation

The scheduler should support randomized module ordering. The objective is to
produce more natural account behaviour.

Future enhancements may include:

- Weighted module selection
- Module cooldowns
- Adaptive scheduling
- AI-assisted scheduling
- Priority modules

## Event-Based Actions

Certain actions should not behave as normal modules. Direct Messages to newly
gained followers are one example.

Workflow:

```text
Session starts
  ↓
New followers detected
  ↓
DM queue created
  ↓
DM module processes queued users
```

These event-driven actions should remain independent from the normal interaction
rotation.

## Long-Term Goal

IGBot should eventually own its own interaction scheduler instead of relying on the
fixed interaction order implemented by InstaAddict.

This idea is intentionally Version 2+ and should not affect Version 1 compatibility.
