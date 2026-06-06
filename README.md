# Ecowitt Weather Station

**Indigo home automation plugin.**

Indigo plugin for Ecowitt weather stations — discovers indoor/outdoor sensors, multi-channel temperature/humidity, wind, rain and solar/UV sensors automatically and exposes live data as native Indigo devices

**Author:** CliveS & Claude Sonnet 4.6
**Platform:** Indigo 2022.1 or later, macOS (Python 3.10+ bundled with Indigo)

*Developed and tested on Indigo 2025.2 / Python 3.13. Older Indigo releases that meet the minimum API version above should also work — the API floor is what Indigo's plugin loader actually checks.*
**Bundle ID:** `com.clives.indigoplugin.ecowitt`
**Version:** 2.2.2

---

## Installation

1. Go to the [Releases page](https://github.com/Highsteads/Ecowitt/releases) and download `Ecowitt.indigoPlugin.zip`
2. Unzip the downloaded file — you will get `Ecowitt.indigoPlugin`
3. Double-click `Ecowitt.indigoPlugin` — Indigo will install it automatically
4. In Indigo: **Plugins → Manage Plugins → Enable** Ecowitt Weather Station
5. Open **Plugins → Ecowitt Weather Station → Configure** and fill in any required fields

---

## Credentials — `IndigoSecrets.py` vs `IndigoSecrets_example.py`

This plugin (along with all CliveS Indigo plugins) reads sensitive values from
a shared master credentials file at:

`/Library/Application Support/Perceptive Automation/IndigoSecrets.py`

| File | Purpose | Real data? | Committed to GitHub? |
|------|---------|------------|----------------------|
| `IndigoSecrets.py` | Working file the plugin reads at runtime. Keep a backup in a password manager. | YES | **NO** — listed in `.gitignore` |
| `IndigoSecrets_example.py` | Template only — empty placeholders. Shipped in the plugin bundle. | NO | YES |

If you do not have `IndigoSecrets.py`, copy `IndigoSecrets_example.py` from
the plugin bundle to `/Library/Application Support/Perceptive Automation/` and rename it to `IndigoSecrets.py`, then fill in your values. Or skip
`IndigoSecrets.py` entirely and enter values via the plugin's configuration
dialog — `IndigoSecrets.py` wins over the dialog when both are set.

If a required value is set in NEITHER source the plugin logs an ERROR
pointing the user to either fill in the matching field or add the key to
`IndigoSecrets.py`.

---

## Logging

Every log line is prefixed with a millisecond timestamp `[HH:MM:SS.mmm]` so
events can be correlated tightly with other CliveS plugins (Device Activity
Monitor uses the same convention).

To turn the prefix off (or back on) at any time:

**Plugins → Ecowitt Weather Station → Toggle Timestamps in Log (on/off)**

The setting is stored in `pluginPrefs` (`enableTimestampLogging`) and persists
across restarts. Defaults to ON.

---

## Repository structure

```
README.md                        ← this file (GitHub displays this)
Ecowitt.indigoPlugin/
├── Contents/
│   ├── Info.plist
│   └── Server Plugin/
│       ├── plugin.py
│       └── ...
└── Contents/Server Plugin/IndigoSecrets_example.py   ← credential template
```

---

## License

GPL-3.0 — see plugin source files for details.
