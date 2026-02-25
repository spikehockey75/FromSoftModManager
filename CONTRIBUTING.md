# Contributing to FromSoft Mod Manager

Thanks for your interest in contributing! This guide covers everything
you need to get started.

---

## Tech Stack

| Layer          | Technology                                          | Notes                                                          |
|----------------|-----------------------------------------------------|----------------------------------------------------------------|
| **UI**         | PySide6 (Qt 6)                                      | Native desktop widgets, dark QSS theme                         |
| **Language**   | Python 3.10+                                        | Type hints used throughout                                     |
| **Mod Loader** | [Mod Engine 3](https://github.com/garyttierney/me3) | CLI-based game launching with TOML profiles                    |
| **Mod Source** | [Nexus Mods](https://www.nexusmods.com)             | SSO auth + REST API for downloads                              |
| **Packaging**  | PyInstaller + Inno Setup                            | Single-directory bundle then Windows installer                 |
| **Platform**   | Windows only                                        | Uses `%APPDATA%`, `%LOCALAPPDATA%`, Steam registry, PowerShell |

---

## Getting Set Up

1. **Clone the repo**

   ```bash
   git clone https://github.com/spikehockey75/FromSoftSeamlessCoOpManager.git
   cd FromSoftSeamlessCoOpManager
   ```

2. **Create a virtual environment and install dependencies**

   ```bash
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```

3. **Run the app**

   ```bash
   .venv\Scripts\python main.py
   ```

4. **Make changes** — edit files, then restart the app to see your changes.

---

## Project Structure

```text
main.py                          Entry point
VERSION                          App version string
requirements.txt                 Python dependencies
app/
├── config/
│   ├── config_manager.py        Config wrapper (config.json)
│   └── game_definitions.py      Game metadata, paths, and defaults
├── core/
│   ├── game_scanner.py          Steam library scanner
│   ├── ini_parser.py            INI file parser with type inference
│   ├── me2_migrator.py          ME2/ME3 profile import and migration
│   ├── me3_service.py           ME3 CLI integration and profile management
│   ├── mod_installer.py         Archive extraction and mod installation
│   ├── mod_updater.py           Version comparison and update checking
│   └── save_manager.py          Save file operations
├── services/
│   ├── nexus_service.py         Nexus Mods REST API client
│   ├── nexus_sso.py             Nexus SSO WebSocket auth flow
│   └── steam_service.py         Steam player count and asset APIs
└── ui/
    ├── main_window.py           Main window with sidebar + content split
    ├── sidebar.py               Game list, player counts, Nexus widget
    ├── game_page.py             Per-game tab container
    ├── nexus_widget.py          Nexus auth widget (SSO + manual key)
    ├── terminal_widget.py       Log output panel
    ├── tabs/
    │   ├── launch_tab.py        Game launcher with cover art and player count
    │   ├── mods_tab.py          Mod cards, trending mods, install/update
    │   ├── saves_tab.py         Save file management
    │   └── settings_tab.py      ME3 profile viewer
    ├── dialogs/
    │   ├── add_mod_dialog.py         Add mod via Nexus URL or local archive
    │   ├── confirm_dialog.py         Confirmation prompts
    │   ├── me2_migration_dialog.py   ME2/ME3 import wizard
    │   ├── me3_setup_dialog.py       First-launch ME3 installer
    │   ├── mod_settings_dialog.py    INI settings editor
    │   └── settings_dialog.py        App settings
    └── widgets/
        └── toggle_switch.py     Animated toggle switch widget
resources/
├── dark_theme.qss               Qt stylesheet (dark purple-navy theme)
├── covers/                      Steam cover art cache
├── headers/                     Steam header image cache
├── logos/                       Steam logo cache
└── icons/                       App icons
build/
├── build.py                     PyInstaller build script
└── installer.iss                Inno Setup installer config
```

### Key areas

- **`app/config/game_definitions.py`** — Dictionary defining each
  supported game (Steam folder, app ID, config paths, defaults, Nexus
  info). This is where you add new games.
- **`app/core/game_scanner.py`** — Discovers Steam libraries across
  all drives via registry and drive probing.
- **`app/core/me3_service.py`** — ME3 CLI wrapper: profile writing,
  game launching, ME3 install/update. See also `ME3_GAME_MAP` for
  game ID mappings.
- **`app/core/me2_migrator.py`** — Imports mods from Mod Engine 2
  configs, existing ME3 profiles, and game folder scans.
- **`app/core/mod_installer.py`** — Archive extraction (zip/7z/rar),
  INI backup/merge, mod installation workflow.
- **`app/ui/tabs/mods_tab.py`** — Mod management UI: install, update,
  enable/disable, trending mods, Nexus integration.
- **`resources/dark_theme.qss`** — App-wide dark theme. Uses
  `#0e0e18` background, `#e94560` accent.

---

## Adding a New Game

1. **Add a game definition** in
   `app/config/game_definitions.py` → `GAME_DEFINITIONS`:

   ```python
   "new_id": {
       "name": "Game Title",
       "steam_app_id": 123456,
       "steam_folder": "GAME FOLDER NAME",
       "config_relative": os.path.join(
           "Game", "ModFolder", "mod_settings.ini"
       ),
       "mod_extract_relative": "Game",
       "save_appdata_folder": "GameSaveFolder",
       "save_prefix": "GS0000",
       "base_ext": ".sl2",
       "coop_ext": ".co2",
       "mod_name": "Game Seamless Co-op",
       "nexus_domain": "gamename",
       "nexus_mod_id": 123,
       "nexus_url": "https://www.nexusmods.com/gamename/mods/123",
       "zip_pattern": r"game.*seamless.*co-?op.*\.zip$",
       "launcher_relative": os.path.join(
           "Game", "ModFolder", "mod_launcher.exe"
       ),
       "mod_marker_relative": os.path.join("Game", "ModFolder"),
       "me3_game_name": "gamename",
       "defaults": {
           "setting_name": "default_value",
       },
   }
   ```

2. **Add ME3 mapping** in
   `app/core/me3_service.py` → `ME3_GAME_MAP`:

   ```python
   "new_id": "me3gamename",
   ```

3. **Test** by installing the game, then clicking **Scan Games** in
   the sidebar. The UI builds dynamically from the definitions.

---

## Coding Conventions

### Python

- **PySide6** for all UI — no web views, no HTML
- Use `os.path` for file path operations (Windows compatibility)
- Background work uses `threading.Thread` with
  `queue.SimpleQueue` for thread-safe UI updates
- Signals (`PySide6.QtCore.Signal`) for cross-widget communication
- Lazy imports inside methods to keep startup fast
- `try/except` with meaningful fallbacks for file operations

### UI / Theme

- All styling via `resources/dark_theme.qss` and inline
  `setStyleSheet()` calls
- Dark theme: `#0e0e18` background, `#1a1a2e` cards,
  `#e94560` accent, `#4ecca3` success
- Object names like `btn_accent`, `btn_success`, `card`
  for QSS targeting
- No emojis in UI text unless specifically requested

### General

- Windows-only is fine — this targets Steam on Windows
- No additional dependencies unless necessary (add to
  `requirements.txt` if needed)
- Keep logic in `app/core/` as pure Python, UI in `app/ui/`

---

## Building the Installer

### Step 1: Build with PyInstaller

```bash
.venv\Scripts\python build\build.py
```

### Step 2: Create installer with Inno Setup

1. Install [Inno Setup 6+](https://jrsoftware.org/isinfo.php)
2. Open `build/installer.iss` and compile (F9)
3. Output: `dist/FromSoftModManager_Setup_v*.exe`

---

## Testing

There's no automated test suite currently. To test your changes:

1. **Run the app** and verify the sidebar loads with detected games
2. **Test each tab** on at least one game:
   - **Mods:** install, update, enable/disable, add via Nexus URL
   - **ME3 Profile:** verify profile viewer shows correct DLLs
     and packages
   - **Saves:** list files, backup, restore, transfer
   - **Launch:** verify game starts via ME3
3. **Test edge cases:**
   - No games installed (sidebar should show "Scan Games" prompt)
   - Game installed but mod not installed (Mods tab should offer
     install)
   - Multiple Steam libraries on different drives
   - Fresh install (no `config.json`) — auto-detection should work

---

## Credits

- **Seamless Co-op mods** by
  [LukeYui](https://github.com/LukeYui)
- **Mod Engine 3** by
  [Gary Tierney](https://github.com/garyttierney/me3)

---

## Submitting Changes

1. Fork the repo and create a feature branch
2. Make your changes following the conventions above
3. Test manually on your own machine
4. Open a pull request with a clear description of what
   changed and why
