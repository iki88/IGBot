# IGBot UI Polish

This is a living project document for reviewed UI and workflow improvements that will be implemented after the core functionality is complete. Update it whenever new UI or workflow improvements are identified.

## High Priority

### Navigation

- Replace separate Start and Stop buttons with one dynamic button.
- Remove double-click-to-open from the Devices page.
- Open phones only through the Manage action.
- Improve running/stopped status presentation.

### Device Workspace

- Add analytics action button to every phone account row.
- Add analytics action button to the Global Accounts page.
- Restore compact action icons similar to the previous production software.
- Improve account action column layout.

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

#### DM

- Move Compose Message editor to the top.
- Reserve a second button beside it for future AI Prompt integration.
- Place limits and advanced settings below the editor.

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
