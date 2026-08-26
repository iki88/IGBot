# scrcpy Bundling Audit

## Audit result

As of Sprint 5.6, the IGBot repository does not contain `scrcpy.exe` or a
scrcpy distribution. The checked-in `IGBot.zip` archive does not contain it
either. No build script, installer script, project configuration, or existing
resource manifest currently installs or references a bundled scrcpy runtime.

The repository contains `IGBot/tools`, but that directory is a Python package
for application code. Third-party executables should not be mixed into that
package.

An `adb.exe` supplied by the development virtual environment's `adbutils`
dependency was found. A separate ADB installation is also available on the
development machine's system `PATH`. Neither location contains scrcpy.

## Standard bundled layout

The permanent Windows bundle should place the complete official scrcpy
distribution at the repository or installed-application root:

```text
IGBot/
├── tools/
│   └── scrcpy/
│       ├── scrcpy.exe
│       ├── adb.exe
│       ├── scrcpy-server
│       └── supporting DLL files from the scrcpy distribution
├── IGBot/
└── run.py
```

The entire distribution must remain together because `scrcpy.exe` depends on
its adjacent server binary and libraries. Only placing `scrcpy.exe` in the
directory is not sufficient.

## Discovery contract

IGBot searches in this order:

1. Bundled application locations, preferring `tools/scrcpy/scrcpy.exe`.
2. The optional `SCRCPY_PATH` environment variable.
3. The system `PATH` through `shutil.which()`.
4. The existing themed unavailable-tool error dialog.

Bundled discovery considers the configured workspace, source checkout,
PyInstaller extraction directory, and frozen executable directory. This keeps
development and future installed builds independent of the process working
directory and avoids absolute paths.
