# Contributing to FromSoft Seamless Co-op Manager

Thanks for your interest in contributing! This guide covers everything you need to get started.

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Backend** | Python 3.8+ / Flask | Single file: `server.py` |
| **Frontend** | Vanilla HTML, CSS, JS | No build tools, no frameworks, no npm |
| **Image Processing** | Pillow | PNG→ICO conversion, Steam cover art cropping |
| **Platform** | Windows only | Uses `%APPDATA%`, PowerShell shortcuts, Steam paths |

There are **no build steps**. Edit a file, restart the server, refresh the browser.

---

## Getting Set Up

1. **Clone the repo**
   ```
   git clone <repo-url> FromSoftSeamlessCoOpManager
   cd FromSoftSeamlessCoOpManager
   ```

2. **Run the installer**
   ```
   install.bat
   ```
   This creates a `.venv` virtual environment and installs Flask + Pillow.

3. **Start the server**
   ```
   run.bat
   ```
   The app opens at `http://127.0.0.1:5000`. When launched via the desktop shortcut or `launch.vbs`, the server runs in the background with no console window.

   > **Tip for development:** Run `run.bat` directly from a terminal so you can see server output and stop it with `Ctrl+C`. The desktop shortcut uses `launch.vbs` which hides the console — not ideal for debugging.

4. **Make changes** — edit files, then:
   - **Python changes (`server.py`):** Stop the server (end `pythonw.exe`/`python.exe` in Task Manager, or `Ctrl+C` if running from a terminal) and re-run `run.bat`
   - **JS/CSS/HTML changes:** Hard-refresh the browser (`Ctrl+Shift+R`)

---

## Project Structure

```
server.py            ← All backend logic (Flask routes, scanner, INI parser)
templates/index.html ← Single HTML template
static/app.js        ← All frontend logic (dashboard, tabs, forms, API calls)
static/style.css     ← All styling (dark theme)
install.bat          ← One-time setup script
launch.vbs           ← Silent launcher (runs run.bat with no console window)
run.bat              ← App launcher (uses pythonw for background execution)
requirements.txt     ← Python dependencies
```

### Key areas in `server.py`

- **`GAME_DEFINITIONS`** — Dictionary defining each supported game (Steam folder name, app ID, config paths, defaults, Nexus URL). This is where you add new games.
- **`scan_for_games()`** — Discovers Steam libraries across all drives and checks for installed games.
- **`/api/settings/<game_id>`** — Reads/writes the mod's `.ini` config file with a custom parser that extracts metadata from comments.
- **`/api/saves/<game_id>`** — Save file listing, transfer, backup, restore, and delete operations.
- **`/api/mod/<game_id>/install`** — Extracts mod zips into the correct game directory.
- **`/api/shortcut/<game_id>`** — Downloads Steam cover art, converts to `.ico`, creates a Windows desktop shortcut.

### Key areas in `static/app.js`

- **`loadConfig()` / `buildGameHome()`** — Fetches game data from the API and renders the landing page card grid.
- **`showGameDetail()`** — Builds the tabbed detail view (Launch, Settings, Saves, Mod Installer).
- **`buildSettingsTab()`** — Dynamically generates form controls from INI metadata with dirty tracking and undo.
- **`buildSavesTab()`** — Transfer cards, backup/restore UI, delete confirmations.
- **`buildModTab()`** — Zip scanner, install flow, cleanup prompts.

---

## Adding a New Game

To add support for another FromSoftware game with a Seamless Co-op mod:

1. **Add a game definition** in `server.py` → `GAME_DEFINITIONS`:
   ```python
   "new_game_id": {
       "name": "Game Title",
       "steam_folder": "GameFolderName",       # Folder name inside steamapps/common/
       "steam_app_id": "123456",               # Steam application ID
       "config_relative": "Game\\ModFolder\\mod_settings.ini",
       "launcher_relative": "Game\\ModFolder\\mod_launcher.exe",
       "mod_marker_relative": "Game\\ModFolder",
       "save_dir_name": "GameSaveFolder",      # Folder name inside %APPDATA%
       "save_ext_base": ".sl2",                # Base game save extension
       "save_ext_coop": ".co2",                # Co-op mod save extension
       "nexus_url": "https://www.nexusmods.com/...",
       "zip_patterns": ["ModName*.zip"],       # Glob patterns to find mod zips in Downloads
       "defaults": {                           # Default INI settings
           "setting_name": "default_value",
       }
   }
   ```

2. **Test** by installing the game and its co-op mod, then clicking **Scan for Games** in the app.

That's it — the frontend dynamically builds UI for any game in the definitions. No HTML or JS changes needed.

---

## Coding Conventions

### Python (`server.py`)

- **No external dependencies** beyond Flask and Pillow — keep it lightweight
- Use `os.path` for all file path operations (Windows compatibility)
- All API endpoints return JSON with consistent shapes (`{"status": "ok", ...}` or `{"error": "message"}`)
- Use `try/except` with meaningful error messages for file operations
- Comments for non-obvious logic, especially INI parsing heuristics

### JavaScript (`static/app.js`)

- **Vanilla JS only** — no jQuery, no React, no TypeScript, no bundlers
- Use `async/await` with `fetch()` for all API calls
- DOM creation via `document.createElement()` — no innerHTML for dynamic content with user data
- Functions are prefixed by their tab/feature area (`buildSettingsTab`, `buildSavesTab`, etc.)
- Confirmation dialogs use the app's built-in modal, not `window.confirm()`

### CSS (`static/style.css`)

- Dark theme throughout — use existing CSS variables and color values for consistency
- BEM-ish naming: `.game-home`, `.home-card`, `.btn-launch-sm`, `.btn-danger-sm`
- Mobile responsiveness is not a priority (this is a desktop-only tool)

### General

- No build steps — the app must work by just running `run.bat`
- No additional dependencies unless absolutely necessary (add to `requirements.txt` if needed)
- Keep everything in as few files as possible — single `server.py`, single `app.js`, single `style.css`
- Windows-only is fine — this targets Steam on Windows

---

## Common Tasks

### Adding a new API endpoint

1. Add the Flask route in `server.py`
2. Call it from `app.js` using `fetch()`
3. Handle errors with try/catch and show user-friendly messages

### Adding a new tab to the game detail view

1. Add a tab button in the `showGameDetail()` function in `app.js`
2. Create a `buildYourTab(gameId)` function that returns a DOM element
3. Wire it up in the tab-switching logic

### Modifying the INI parser

The parser in `server.py` reads mod INI files and extracts:
- Setting names and current values
- Comments above each setting (used as descriptions)
- Metadata from comments to determine control types (dropdowns, ranges, etc.)

Be careful with changes here — each game's mod has slightly different comment formatting.

---

## Testing

There's no automated test suite currently. To test your changes:

1. **Run the app** and verify the landing page loads with game cards
2. **Test each tab** on at least one game:
   - Settings: change a value, check dirty tracking, save, undo, reset defaults
   - Saves: list files, make a backup, restore it, test transfers
   - Mod Installer: verify zip detection, install, cleanup prompt
   - Launch: verify the launcher starts
3. **Test edge cases:**
   - No games installed
   - Game installed but mod not installed (only Mod Installer tab should show)
   - Multiple Steam libraries on different drives

---

## Submitting Changes

1. Fork the repo and create a feature branch
2. Make your changes following the conventions above
3. Test manually on your own machine
4. Open a pull request with a clear description of what changed and why

---

## Ideas for Contribution

Looking for something to work on? Here are some areas that could use help:

- **New game support** — add definitions for other FromSoft co-op mods as they release
- **Auto-update checking** — detect when a newer mod version is available on Nexus
- **Backup scheduling** — automatic periodic save backups
- **Import/export settings** — share INI configs between players
- **UI improvements** — animations, transitions, better mobile layout (if anyone wants it)
- **Error handling** — more graceful handling of edge cases (permission errors, locked files, etc.)
- **Localization** — support for languages other than English
