# Codex Reset Check

A lightweight [Alfred](https://www.alfredapp.com/) workflow that inspects your Codex usage windows and available reset credits using your existing local Codex Desktop session.

Reads `~/.codex/auth.json` and calls the same internal endpoints used by the desktop client — no API key needed.

## Features

- Displays the current 5-hour usage window.
- Displays the current weekly usage window.
- Lists available reset credits with human-readable expiry text.
- Uses your existing Codex Desktop login. No additional credentials required.

## Requirements

- macOS
- [Alfred](https://www.alfredapp.com/) with Powerpack (workflow support)
- Codex Desktop — installed and signed in

## Install

1. Download the latest `.alfredworkflow` from the [Releases page](https://github.com/g17ui/codex-reset-check/releases/latest).
2. Open the downloaded file to let Alfred import the workflow.
3. Trigger Alfred and type `codexreset`.

Each trigger performs a fresh request and returns the latest available data.

## Repository Layout

```
.
├── .github/workflows/release.yml      # CI: automatic release on tag push
├── README.md
└── workflow
    ├── codex_reset.py                  # main workflow logic
    └── info.plist                      # Alfred workflow metadata
```

## How It Works

A single Script Filter powered by `workflow/codex_reset.py`:

1. Reads the local Codex auth state from `~/.codex/auth.json`.
2. Sends two read-only GET requests:
   - `GET https://chatgpt.com/backend-api/wham/usage`
   - `GET https://chatgpt.com/backend-api/wham/rate-limit-reset-credits`
3. Formats the JSON responses into Alfred Script Filter items.

## Privacy & Safety

- **Read-only.** This workflow never redeems reset credits or modifies your Codex account.
- **No external storage.** Your token is never written outside the existing local auth file.

## Limitations

- Endpoints are internal and may change without notice.
- Returned fields may differ by account type, region, plan, or Codex Desktop version.
- Requires a valid local Codex Desktop sign-in state.
