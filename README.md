# FromSoft Mod Manager

Skip the manual mod setup headaches — FromSoft Mod Manager automatically finds your Steam games, installs co-op mods from Nexus with one click, and keeps everything up to date. Connect your Nexus account, pick your game, and you're playing co-op in minutes. Saves, settings, and mod loading through Mod Engine 3 are all handled for you.

> **Note:** This is a **manager tool only**. The Seamless Co-op mods
> are created by [LukeYui](https://github.com/LukeYui). All credit
> for the mods goes to them.
>
> Game launching and mod loading is powered by
> [Mod Engine 3](https://github.com/garyttierney/me3)
> by Gary Tierney.

![Windows](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

> **Quick install:** Download the installer from the latest
> [Release](https://github.com/spikehockey75/FromSoftSeamlessCoOpManager/releases)
> and run it.

---

## Supported Games

| Game                                  | Co-op Mod                      | Nexus Mods                                                                              |
|---------------------------------------|--------------------------------|-----------------------------------------------------------------------------------------|
| **Armored Core 6: Fires of Rubicon**  | AC6 Seamless Co-op             | [Nexus page](https://www.nexusmods.com/armoredcore6firesofrubicon/mods/3)               |
| **Dark Souls Remastered**             | DSR Seamless Co-op             | [Nexus page](https://www.nexusmods.com/darksoulsremastered/mods/899)                    |
| **Dark Souls III**                    | DS3 Seamless Co-op             | [Nexus page](https://www.nexusmods.com/darksouls3/mods/1895)                            |
| **Elden Ring**                        | Elden Ring Seamless Co-op      | [Nexus page](https://www.nexusmods.com/eldenring/mods/510)                              |
| **Elden Ring Nightreign**             | ER Nightreign Seamless Co-op   | [Nexus page](https://www.nexusmods.com/eldenringnightreign/mods/3)                      |
| **Sekiro: Shadows Die Twice**         | — (ME3 mod loading only)       | [Nexus page](https://www.nexusmods.com/sekiro)                                          |

The app auto-detects installed Steam games by scanning all library
folders across all drives.

---

## Features

### Mod Management

- **One-click install** from Nexus Mods — paste a URL or browse
  trending/recommended mods
- **Automatic update checking** against Nexus Mods versions
- **Enable/disable** individual mods via toggle switches
- **Archive support** — `.zip`, `.7z`, and `.rar` mod archives
- **Progress tracking** — download and install progress shown
  in-dialog
- **Add third-party mods** by pasting a Nexus URL or selecting
  a local archive

### Mod Engine 3 Integration

- Generates and manages ME3 TOML profiles per game
- Structured profile viewer showing native DLLs and asset packages
- Collapsible raw TOML view for power users
- Games launched via ME3 for proper DLL injection and asset loading
- Auto-downloads ME3 on first launch if not installed

### Nexus Mods Integration

- **OAuth 2.0 authentication** — click "Authorize with Nexus Mods",
  approve in browser, done (no copy-paste needed)
- Automatic token refresh — stays connected across sessions
- User profile display in sidebar
- Trending and recommended mods per game
- Direct download with Nexus Premium support

### Mod Settings

- Edit mod `.ini` settings through a clean dialog UI
- Smart type inference — dropdowns, number fields, and text inputs
  based on INI comments
- Change highlighting and save confirmation
- Reset to defaults

### Save Manager

- View base game saves (`.sl2`) and co-op saves (`.co2`)
- **Transfer** saves between base and co-op formats
- **Backup and restore** with timestamps
- Ban risk warnings for co-op-to-base transfers

### Game Launching

- Launch via **Mod Engine 3** with all mods loaded
- Fallback to direct co-op launcher for non-ME3 games
- Error detection via ME3 log file checking
- Desktop shortcut creation
- Live Steam player counts (refreshes every 60 seconds)

---

## Installation

### Prerequisites

- **Windows 10/11** (64-bit)
- **Steam** with at least one supported game installed
- **Mod Engine 3** — the app will download and install it
  automatically on first launch
- **Nexus Mods account** — required for downloading and updating
  mods ([create a free account](https://users.nexusmods.com/register))

### From Release (Recommended)

1. Download `FromSoftModManager_Setup_v*.exe` from the latest
   [GitHub Release](https://github.com/spikehockey75/FromSoftSeamlessCoOpManager/releases)
2. Run the installer — it installs to
   `%LOCALAPPDATA%\FromSoftModManager`
3. Launch from Start Menu or desktop shortcut
4. On first launch, the app will prompt to install Mod Engine 3
   if not found

### From Source (Development)

```bash
git clone https://github.com/spikehockey75/FromSoftSeamlessCoOpManager.git
cd FromSoftSeamlessCoOpManager
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

---

## Building the Installer

Building the distributable `.exe` installer is a two-step process:

### Step 1: Build the app with PyInstaller

```bash
.venv\Scripts\python build\build.py
```

This runs PyInstaller and outputs the bundled app to
`dist/FromSoftModManager/`. The build script:

- Bundles all Python code, PySide6, and dependencies into
  a single directory
- Includes the `resources/` folder (theme, cover art, logos)
  and `VERSION` file
- Produces `dist/FromSoftModManager/FromSoftModManager.exe`

### Step 2: Create the installer with Inno Setup

1. Install [Inno Setup 6+](https://jrsoftware.org/isinfo.php) (free)
2. Open `build/installer.iss` in Inno Setup
3. Click **Build > Compile** (or press F9)
4. The installer is created at
   `dist/FromSoftModManager_Setup_v2.0.0.exe`

The installer:

- Installs to `%LOCALAPPDATA%\FromSoftModManager` (no admin required)
- Creates Start Menu and optional desktop shortcuts
- Includes an uninstaller
- Prompts to download ME3 if not already installed

---

## How to Use

### First Launch

1. Open the app — it will prompt to install Mod Engine 3 if needed
2. Click **Scan Games** in the sidebar — scans all drives for
   Steam libraries and games
3. Detected games appear in the sidebar with live player counts

### Connecting Nexus Mods

1. Click **Connect Account** in the sidebar
2. Click **Authorize with Nexus Mods** — your browser opens
3. Click "Authorize" on the Nexus page — the app connects
   automatically
4. Your Nexus username appears in the sidebar

### Managing Mods

- **Mods tab** — install, update, enable/disable mods;
  browse trending mods
- **ME3 Profile tab** — view the ME3 mod loading configuration
  (ME3-supported games only)
- **Saves tab** — manage save files, backups, and transfers

### Adding Mods

- Click **Add Mod** → paste a Nexus Mods URL
  (e.g., `https://www.nexusmods.com/eldenring/mods/510`)
- Or select a local `.zip` / `.7z` / `.rar` archive
- Progress bar shows download and install status

### Launching Games

Click the **Play** button in the sidebar. Games with ME3 support
are launched via Mod Engine 3 for proper mod loading.

---

## Project Structure

```text
fromsoft_coop_manager/
├── main.py                      Entry point
├── VERSION                      App version string
├── requirements.txt             Python dependencies
├── app/
│   ├── config/
│   │   ├── config_manager.py    Config wrapper (config.json)
│   │   └── game_definitions.py  Game metadata, paths, and defaults
│   ├── core/
│   │   ├── game_scanner.py      Steam library scanner
│   │   ├── ini_parser.py        INI file parser with type inference
│   │   ├── me2_migrator.py      Mod Engine 2 → ME3 migration
│   │   ├── me3_service.py       ME3 CLI integration
│   │   ├── mod_installer.py     Archive extraction and mod install
│   │   ├── mod_updater.py       Version comparison and updates
│   │   └── save_manager.py      Save file operations
│   ├── services/
│   │   ├── nexus_service.py     Nexus Mods REST API client
│   │   ├── nexus_oauth.py       Nexus OAuth 2.0 PKCE auth flow
│   │   └── steam_service.py     Steam player count and asset APIs
│   └── ui/
│       ├── main_window.py       Main window with sidebar + content
│       ├── sidebar.py           Game list, player counts, Nexus
│       ├── game_page.py         Per-game tab container
│       ├── nexus_widget.py      Nexus auth widget (OAuth 2.0)
│       ├── terminal_widget.py   Log output panel
│       ├── tabs/
│       │   ├── launch_tab.py    Game launcher with cover art
│       │   ├── mods_tab.py      Mod cards, trending, install
│       │   ├── saves_tab.py     Save file management
│       │   └── settings_tab.py  ME3 profile viewer
│       ├── dialogs/
│       │   ├── add_mod_dialog.py      Add mod via URL or archive
│       │   ├── confirm_dialog.py      Confirmation prompts
│       │   ├── me2_migration_dialog.py  ME2 migration wizard
│       │   ├── me3_setup_dialog.py    First-launch ME3 installer
│       │   ├── mod_settings_dialog.py INI settings editor
│       │   └── settings_dialog.py     App settings
│       └── widgets/
│           └── toggle_switch.py  Animated toggle switch widget
├── resources/
│   ├── dark_theme.qss           Qt stylesheet (dark theme)
│   ├── covers/                  Steam cover art cache
│   ├── headers/                 Steam header image cache
│   ├── logos/                   Steam logo cache
│   └── icons/                   App icons
└── build/
    ├── build.py                 PyInstaller build script
    └── installer.iss            Inno Setup installer config
```

---

## Dependencies

| Package                | Purpose                                            |
| ---------------------- | -------------------------------------------------- |
| `PySide6`              | Qt 6 UI framework                                  |
| `requests`             | HTTP client for API calls                          |
| `tomlkit` / `tomli-w`  | TOML reading/writing for ME3 profiles              |
| `py7zr`                | 7z archive extraction                              |
| `rarfile`              | RAR archive extraction (requires WinRAR or 7-Zip)  |
| `pyinstaller`          | Build tooling (dev only)                           |

---

## FAQ

### Can I get banned for using this?

**No.** The co-op mods prevent you from connecting to FromSoftware's
matchmaking servers and use separate save files. There is no risk of
bans from normal use.

> Do **not** transfer co-op save files back to base game saves and
> then play online — this risks a ban.

### The app didn't find my game

- Make sure the game is installed via **Steam**
- Click **Scan Games** to re-detect
- The co-op mod does not need to be pre-installed — you can install
  it from the Mods tab

### RAR mods fail to extract

RAR extraction requires **WinRAR** or **7-Zip** to be installed on
your system. The app checks these default paths:

- `C:\Program Files\WinRAR\UnRAR.exe`
- `C:\Program Files\7-Zip\7z.exe`
- `C:\Program Files (x86)\` variants

### Can I add support for another game?

Add a new entry to `GAME_DEFINITIONS` in
`app/config/game_definitions.py` and (if ME3-supported) add the game
to `ME3_GAME_MAP` in `app/core/me3_service.py`.

---

## Technical Details

| Component        | Details                                                    |
| ---------------- | ---------------------------------------------------------- |
| **UI Framework** | PySide6 (Qt 6) with Fusion base style                      |
| **Mod Loader**   | Mod Engine 3 CLI (`me3 launch -g <game>`)                  |
| **Nexus Auth**   | OAuth 2.0 PKCE with automatic token refresh                |
| **Packaging**    | PyInstaller (onedir) then Inno Setup installer             |
| **Config**       | JSON config file (`config.json`)                           |
| **Theme**        | Custom QSS dark theme (#0e0e18 bg, #e94560 accent)         |
| **Archives**     | zip (builtin), 7z (py7zr), RAR (rarfile + WinRAR/7-Zip)    |
