# Desktop Packaging Handoff

Packaging P1 provides a thin, cross-platform Tk GUI and direct shared Python orchestration:

```sh
PYTHONPATH=src .venv/bin/python3 -m futures_intelligence.gui
```

The Tkinter launcher calls the same bounded deterministic Huatai demo orchestration as the CLI. It does not ship a standalone application bundle or executable yet. Running from source requires the project dependencies and a Python installation with Tk support.

A later P2 packaging phase is intended to turn this entry point into distributable artifacts:

- macOS: `.app` and `.dmg`;
- Windows: `.exe` and `.zip`;
- reproducible build instructions or release automation.

That future work may use PyInstaller and GitHub Actions, but neither is implemented or configured in P1. P2 should verify bundled dependencies and certificates where applicable and test the resulting artifacts on both target operating systems. It must preserve the shared application boundary rather than copying demo logic into platform-specific launchers.
