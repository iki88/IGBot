# IGBot Roadmap

This roadmap is the single source of truth for IGBot project progress. Preserve completed milestones and update this file whenever a milestone is completed.

## Completed

### Sprint 4A

- Device onboarding and persistent device inventory.
- Add Device and Rename Device.
- Archived workspace.
- Desktop UI refinements.

### Sprint 4B

- Transfer Account, Archive Account, and Restore Account.
- Delete Archived Account.
- Archived account search.
- Open Account Folder.
- Live Log integration and background workers.
- Atomic account configuration updates and rollback protection.

### Sprint 5.0

- Workspace navigation and screen hierarchy.
- Devices workspace and global Accounts workspace.
- Archived workspace and Activity Log page.
- Global Settings page.
- Account page with module tabs.
- Context-aware toolbars and account actions.

### Sprint 5.1

- Compact, icon-based phone workspace toolbar.
- Final account table columns and prepared Status column.
- Dense account rows with refined spacing, alignment, sizing, and typography.
- Improved dark-theme toolbar and table presentation.
- Disabled View Phone control awaiting scrcpy integration.

### Sprint 5.2

- Phone-scoped Add Account dialog with username and password validation.
- Account initialization from existing InstaAddict configuration templates.
- Automatic phone assignment, workspace refresh, device counters, and Live Log entries.

### Sprint 5.3

- Account Overview with editable credentials and masked password visibility controls.
- App Cloner application ID configuration and clearly disabled future account controls.
- Atomic, verified account settings updates preserving YAML formatting and comments.

### Sprint 5.4

- Reusable Follow configuration interface with validation and dirty-state tracking.
- Atomic Follow settings persistence preserving existing YAML content.
- Read-only Android application package selector.
- Account Save Changes keyboard shortcut.

### Sprint 5.5

- Account Timer configuration with exact multi-schedule value preservation.
- Reusable scheduling, randomization, daily behaviour, and warmup sections.
- Timer validation integrated with atomic account configuration saving.
- Follow and Timer bindings verified against the engine configuration vocabulary.
- Obsolete IGBot-only YAML mappings removed during atomic account saves.

### Sprint 5.5.1

- IGBot-owned account metadata with persistent account credentials.
- Atomic credential editing and account-directory rename handling.
- Embedded password visibility control and refined account-page presentation.
- Foreground Android application ID detection with deferred saving.

### Sprint 5.6

- Managed scrcpy phone viewing from Devices and Phone workspaces.
- One scrcpy session per Android device with automatic process cleanup.
- Connected, authorized-device validation and bundled-tool discovery.
- Complete foreground Application ID detection with deferred persistence and Live Log diagnostics.

### Sprint 5.7

- Isolated InstaAddict account runtime orchestration.
- Responsive Start and graceful Stop controls with lifecycle states.
- Runtime output forwarding to Live Log and concurrent-session-ready workers.

### Sprint 5.7.4

- One persistent Phone Scheduler worker per managed Android phone.
- Sequential timer discovery and account selection with disabled-session handling.
- Waiting scheduler lifecycle, scheduling decision logs, and phone-scoped Start/Stop.

### Sprint 5.8

- Engine-compatible Unfollow configuration interface.
- Unfollow modes, limits, behaviour, file targets, validation, and status indicator.

### Sprint 5.9

- Engine-compatible Like configuration interface.
- Like interaction, limits, media behaviour, post files, validation, and status indicator.

### Sprint 5.10

- Engine-compatible Story configuration interface.
- Story session settings, limits, validation, dirty state, and status indicator.

### Sprint 5.11

- Engine-compatible Direct Message configuration interface.
- DM limits, recipient filtering, message-bank editing, validation, and status indicator.
- Transparent atomic persistence across config.yml, filters.yml, and pm_list.txt.

## Missing Features From Old Bot

### UI

- [x] View Phone using scrcpy.
- [x] Runtime status indicators.

### Devices

- [ ] Today dialog.
- [x] Start phone scheduler.
- [x] Stop phone scheduler and active account runtime.
- [ ] Device statistics.

### Accounts

- [ ] Statistics page.
- [ ] Copy Settings.
- [ ] Ignore List.
- [ ] Export Account.
- [ ] Delete Cache.

### Automation

- [x] Timer configuration interface (execution not implemented).
- [x] Follow configuration interface (execution not implemented).
- [x] Unfollow configuration interface (execution not implemented).
- [x] Like configuration interface (execution not implemented).
- [ ] Comment.
- [x] Story configuration interface (execution not implemented).
- [x] DM configuration interface (execution not implemented).
- [ ] Post.
- [ ] Reels.
- [ ] Share.

### Global

- [x] Phone Scheduler lifecycle and timer-selection foundation.
- [ ] Session history.
- [ ] Session queue.
- [ ] Live automation monitor.

## Planned Sprints

### Sprint 6

Automation engine integration.

### Sprint 7

Storage redesign and migration.
