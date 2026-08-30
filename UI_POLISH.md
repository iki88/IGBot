# IGBot UI Polish

This is a living project document for reviewed UI and workflow improvements that will be implemented after the core functionality is complete. Update it whenever new UI or workflow improvements are identified.

## High Priority

### Completed workflow refinements

- Follow now presents the Version 1 production workflow in the order Enable, Method, Settings, Additional Settings, and Filters.
- Follow methods are limited to Followers, Followings, and Specific Users while lower-priority engine sources remain compatible but hidden.
- Required and blocked Follow words use the shared one-entry-per-line editor, and internal engine safeguards remain outside the normal operator controls.
- Follow filters use operator-oriented labels, standard checkboxes for word-list activation, paired numeric ranges, and vertically arranged language fields.
- Follow now uses the product workflow: Enable Follow, Follow Method, Follow Actions, Follow Settings, Additional Follow Settings, and Schedule. Unsupported delay, mute, tagged-account, and weekday controls remain UI-only runtime extensions.
- Follow Schedule is collapsed by default with vertical weekdays, Follow action sizing is consistent, and every module tab uses the same filled green/grey state indicator.
- Module state is rendered with fixed-size colored tab icons so selected-tab text styling cannot obscure enabled state. Follow language and alphabet filters use the shared one-entry-per-line popup editor.
- Follow Actions now share one alignment grid, and popup-backed checkbox labels use a zero-padding link style aligned with ordinary checkbox text.
- Numeric configuration controls ignore mouse-wheel input globally while retaining keyboard and spin-arrow editing.
- Sidebar navigation now fits its normal contents without a redundant scrollbar and scrolls only when required.
- Unfollow now mirrors Follow's operator-focused structure: source-only methods, shared Min/Max actions, behavioral modifiers, popup-managed usernames, no profile-filter section, and a collapsed weekday schedule.
- Follow and Unfollow action fields now share consistent fixed widths and alignment; popup-backed labels remain blue and pointer-enabled without underline styling.
- Shared checkbox rows now use consistent height and spacing, clickable labels share native checkbox text geometry, and numeric inputs are keyboard-only without wheel changes or spin buttons.
- Like now follows the finalized product module structure with production-focused methods, aligned actions, useful media settings, engine-backed filters, and a collapsed weekday schedule.
- Like view-time controls now sit with Like Actions, and the single Minimum Posts filter no longer reserves paired-field space.
- Timer now contains only operator-facing Start Time and End Time fields while transparently translating standard time notation to engine working hours.
- Overview now presents one Account Information section for credentials, Instagram App, detection, and account-specific Tag metadata.
- Overview keeps Detect inline with Instagram App, uses compact account-field spacing, and provides concise Tag examples.
- DM now follows the operator workflow: two recipient methods, popup-managed messages, aligned actions, concise production settings, and a collapsed schedule.
- DM now uses a dedicated single-message editor with multiline, spintax, and emoji support; unsupported delay and private/empty-profile controls are no longer exposed.
- DM method controls now use consistent checkbox styling, with UI-only send-delay controls and a new-follower check interval that is enabled only for the New Followers method.

### Navigation

- [x] Replace separate Start and Stop buttons with one dynamic button.
- Remove double-click-to-open from the Devices page.
- Open phones only through the Manage action.
- Improve running/stopped status presentation.

### Device Workspace

- [x] Add analytics action button to every phone account row.
- [x] Add analytics action button to the Global Accounts page.
- [x] Restore compact action icons similar to the previous production software.
- [x] Improve account action column layout.
- [x] Keep row actions focused on Analytics and Edit while workspace actions remain in the toolbar.
- [x] Standardize compact device runtime, settings, and delete actions.
- [x] Use a clear gear for Device Settings and keep Phone Account rows limited to Analytics, Edit, and Archive.

### Typography

- [x] Increase readability.
- [x] Improve font weight.
- [x] Improve contrast throughout the application.
- [x] Improve numeric input visibility.

### Icons

- Replace placeholder Qt icons.
- Adopt one consistent icon set throughout the application.
- Improve toolbar icons.
- Improve action icons.

### Controls

- [x] Improve checkbox visibility.
- Replace Enable/Disable checkboxes with modern switches where appropriate.
- [x] Improve input field styling.
- [x] Improve hover states.
- [x] Improve section headers.

### Modules

- [x] Use compact module-owned source controls with the shared Target Editor dialog.
- [x] Keep Account and Template editor tab presentation identical.
- [x] Treat target sources as module methods without a duplicate Sources section.
- [x] Keep configuration sections permanently visible in continuous scrolling pages.
- [x] Standardize interaction modules as Enable, Method, Settings, supported Additional Settings, and supported Filters.
- [x] Refine Like around production methods, popup-backed word filters, and optional profile filters.

#### DM

- [x] Move the message editor directly below DM Method.
- [x] Reserve a second button beside it for future AI Prompt integration.
- [x] Place DM actions and additional settings below the editor.

Future modules should follow a consistent layout:

1. Enable
2. Primary editor / main content
3. Configuration
4. Limits
5. Advanced

### Runtime

Changing any execution-related configuration should automatically stop the Phone Scheduler.

This includes:

- Add Account
- Rename Account
- Transfer
- Archive
- Restore
- Delete
- Timer changes
- Application ID changes
- Device assignment changes

The scheduler remains stopped until the operator explicitly presses Start again.

## Future Ideas

Placeholder for future UX improvements discovered during development.
