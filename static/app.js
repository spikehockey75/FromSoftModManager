// ================================================================
// FromSoft Seamless Co-op Manager — Frontend logic
// ================================================================

const $  = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const tabBar   = $("#tab-bar");
const panels   = $("#panels");
const landing  = $("#landing");
const scanning = $("#scanning");
const noGames  = $("#no-games");
const gameHome = $("#game-home");
const scanBtn  = $("#btn-scan");
const scanStat = $("#scan-status");

let currentGames = {};      // game_id → {name, config_path, save_dir, ...}
let activeTab    = null;    // currently selected game_id
let settingsCache = {};     // game_id → sections data
let originalValues = {};    // game_id → { key: originalValue }
let defaultValues = {};     // game_id → { key: defaultValue }
let dirtyGames = new Set(); // game_ids with unsaved changes

// ─── Toast ───────────────────────────────────────────────────
function toast(message, type = "info", duration = 3000) {
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    $("#toasts").appendChild(el);
    setTimeout(() => { el.remove(); }, duration);
}

// ─── Confirm modal ───────────────────────────────────────────
let _confirmResolve = null;
function confirm(title, body) {
    return new Promise(resolve => {
        _confirmResolve = resolve;
        $("#confirm-title").textContent = title;
        $("#confirm-body").innerHTML = body;
        $("#confirm-ok").onclick = () => {
            _confirmResolve = null;
            hide($("#confirm-modal"));
            resolve(true);
        };
        show($("#confirm-modal"));
    });
}
function closeConfirm() {
    hide($("#confirm-modal"));
    if (_confirmResolve) { _confirmResolve(false); _confirmResolve = null; }
}

// ─── Helpers ─────────────────────────────────────────────────
function prettifyKey(key) {
    return key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}
function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(2) + " MB";
}
function formatDate(iso) {
    return new Date(iso).toLocaleString();
}
function show(el)  { el.classList.remove("hidden"); }
function hide(el)  { el.classList.add("hidden"); }

function setLoading(on) {
    scanBtn.disabled = on;
    if (on) {
        hide(landing); hide(noGames); hide(tabBar); hide(gameHome);
        panels.innerHTML = "";
        show(scanning);
    } else {
        hide(scanning);
    }
}

// ─── Scan ────────────────────────────────────────────────────
async function doScan() {
    setLoading(true);
    try {
        const res = await fetch("/api/scan", { method: "POST" });
        const cfg = await res.json();
        handleConfig(cfg);
        toast("Scan complete", "success");
    } catch (err) {
        toast("Scan failed: " + err.message, "error");
        setLoading(false);
        show(landing);
    }
}

// ─── Load existing config on page load ───────────────────────
async function loadConfig() {
    try {
        const res = await fetch("/api/games");
        const cfg = await res.json();
        if (cfg.games && Object.keys(cfg.games).length > 0) {
            handleConfig(cfg);
        } else if (!cfg.last_scan) {
            // First launch — no games found and never scanned before: auto-scan
            doScan();
        }
    } catch (_) {}
}

// ─── Process config data ─────────────────────────────────────
function handleConfig(cfg) {
    setLoading(false);
    currentGames = cfg.games || {};
    const ids = Object.keys(currentGames);

    if (cfg.last_scan) {
        const d = new Date(cfg.last_scan);
        scanStat.textContent = `Last scan: ${d.toLocaleString()}`;
    }

    if (ids.length === 0) {
        show(noGames); hide(gameHome); hide(tabBar);
        return;
    }

    hide(landing); hide(noGames); hide(tabBar);
    panels.innerHTML = "";
    activeTab = null;
    buildGameHome(ids);
}

// ================================================================
// Game Home — card grid landing page
// ================================================================
function buildGameHome(gameIds) {
    gameHome.innerHTML = "";
    for (const id of gameIds) {
        const game = currentGames[id];
        const card = document.createElement("div");
        card.className = "home-card";

        // Cover art
        const artWrap = document.createElement("div");
        artWrap.className = "home-card-art";
        if (game.steam_app_id) {
            const img = document.createElement("img");
            img.src = `https://cdn.cloudflare.steamstatic.com/steam/apps/${game.steam_app_id}/library_600x900.jpg`;
            img.alt = game.name;
            img.draggable = false;
            artWrap.appendChild(img);
        }
        card.appendChild(artWrap);

        // Info area
        const info = document.createElement("div");
        info.className = "home-card-info";

        const nameEl = document.createElement("div");
        nameEl.className = "home-card-name";
        nameEl.textContent = game.name;
        info.appendChild(nameEl);

        // Mod status badge
        const badge = document.createElement("div");
        badge.className = `home-card-badge ${game.mod_installed ? "badge-installed" : "badge-missing"}`;
        badge.textContent = game.mod_installed ? "Co-op Mod Installed" : "Mod Not Installed";
        info.appendChild(badge);

        // Action buttons
        const actions = document.createElement("div");
        actions.className = "home-card-actions";

        if (game.mod_installed && game.launcher_exists) {
            const launchBtn = document.createElement("button");
            launchBtn.className = "btn btn-launch-sm";
            launchBtn.innerHTML = '<span class="btn-icon">&#x1F680;</span> Launch Co-op';
            launchBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                launchBtn.disabled = true;
                launchBtn.innerHTML = '<span class="btn-icon">&#x23F3;</span> Launching...';
                try {
                    const res = await fetch(`/api/launch/${id}`, { method: "POST" });
                    const d = await res.json();
                    if (res.ok) {
                        toast(d.message, "success");
                        launchBtn.innerHTML = '<span class="btn-icon">&#x2705;</span> Launched!';
                    } else {
                        toast(d.error, "error");
                    }
                } catch (err) {
                    toast(err.message, "error");
                }
                setTimeout(() => {
                    launchBtn.disabled = false;
                    launchBtn.innerHTML = '<span class="btn-icon">&#x1F680;</span> Launch Co-op';
                }, 3000);
            });
            actions.appendChild(launchBtn);
        }

        const manageBtn = document.createElement("button");
        manageBtn.className = "btn btn-manage";
        manageBtn.innerHTML = '<span class="btn-icon">&#x2699;</span> Manage';
        manageBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            openGameDetail(id);
        });
        actions.appendChild(manageBtn);

        // Desktop shortcut button (only when mod is installed & launcher exists)
        if (game.mod_installed && game.launcher_exists) {
            const shortcutBtn = document.createElement("button");
            shortcutBtn.className = "btn btn-shortcut";
            shortcutBtn.innerHTML = '<span class="btn-icon">&#x1F4CC;</span> Desktop Shortcut';
            shortcutBtn.title = `Create a desktop shortcut for ${game.name} Co-op`;
            shortcutBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                shortcutBtn.disabled = true;
                shortcutBtn.innerHTML = '<span class="btn-icon">&#x23F3;</span> Creating...';
                try {
                    const res = await fetch(`/api/shortcut/${id}`, { method: "POST" });
                    const d = await res.json();
                    if (res.ok) {
                        toast(d.message, "success");
                        shortcutBtn.innerHTML = '<span class="btn-icon">&#x2705;</span> Created!';
                    } else {
                        toast(d.error, "error");
                        shortcutBtn.innerHTML = '<span class="btn-icon">&#x1F4CC;</span> Desktop Shortcut';
                        shortcutBtn.disabled = false;
                    }
                } catch (err) {
                    toast(err.message, "error");
                    shortcutBtn.innerHTML = '<span class="btn-icon">&#x1F4CC;</span> Desktop Shortcut';
                    shortcutBtn.disabled = false;
                }
                setTimeout(() => {
                    shortcutBtn.disabled = false;
                    shortcutBtn.innerHTML = '<span class="btn-icon">&#x1F4CC;</span> Desktop Shortcut';
                }, 4000);
            });
            actions.appendChild(shortcutBtn);
        }

        info.appendChild(actions);
        card.appendChild(info);
        gameHome.appendChild(card);
    }
    show(gameHome);
}

// ─── Navigate into a game's detail view ──────────────────────
async function openGameDetail(gameId) {
    hide(gameHome);
    activeTab = gameId;
    show(tabBar);
    buildDetailHeader(gameId);
    if (!panels.querySelector(`.game-panel[data-game="${gameId}"]`)) {
        await buildGamePanel(gameId);
    } else {
        panels.querySelectorAll(".game-panel").forEach(p => {
            p.classList.toggle("active", p.dataset.game === gameId);
        });
    }
}

// ─── Back navigation header in tab bar ──────────────────────
function buildDetailHeader(gameId) {
    const game = currentGames[gameId];
    tabBar.innerHTML = "";

    const backBtn = document.createElement("button");
    backBtn.className = "btn-back";
    backBtn.innerHTML = '&#x2190; All Games';
    backBtn.addEventListener("click", async () => {
        if (activeTab && dirtyGames.has(activeTab)) {
            const stayed = await promptUnsavedIfNeeded(activeTab);
            if (stayed) return;
        }
        hide(tabBar);
        panels.querySelectorAll(".game-panel").forEach(p => p.classList.remove("active"));
        activeTab = null;
        // Re-fetch games so mod status / installs are up to date
        await loadConfig();
    });
    tabBar.appendChild(backBtn);

    const titleEl = document.createElement("span");
    titleEl.className = "detail-header-title";
    if (game.steam_app_id) {
        const icon = document.createElement("img");
        icon.className = "tab-icon";
        icon.src = `https://cdn.cloudflare.steamstatic.com/steam/apps/${game.steam_app_id}/capsule_231x87.jpg`;
        icon.alt = game.name;
        icon.draggable = false;
        titleEl.appendChild(icon);
    }
    const label = document.createElement("span");
    label.textContent = game.name;
    titleEl.appendChild(label);
    tabBar.appendChild(titleEl);
}

// ================================================================
// Build the full game panel (sub-tabs: Launch + Settings + Saves + Installer)
// ================================================================
async function buildGamePanel(gameId) {
    const game = currentGames[gameId];
    const panel = document.createElement("div");
    panel.className = "game-panel active";
    panel.dataset.game = gameId;

    // Sub-tab bar
    const subBar = document.createElement("div");
    subBar.className = "sub-tab-bar";

    const btnLaunch = document.createElement("button");
    btnLaunch.className = "sub-tab-launch";
    btnLaunch.innerHTML = '<span class="btn-icon">&#x1F3AE;</span> Launch Co-op';

    const btnSettings = document.createElement("button");
    btnSettings.textContent = "Mod Settings";

    const btnSaves = document.createElement("button");
    btnSaves.textContent = "Save Manager";

    const btnInstaller = document.createElement("button");
    btnInstaller.textContent = "Mod Installer";

    subBar.appendChild(btnLaunch);
    subBar.appendChild(btnSettings);
    subBar.appendChild(btnSaves);
    subBar.appendChild(btnInstaller);
    panel.appendChild(subBar);

    // Sub-panels
    const launchPanel = document.createElement("div");
    launchPanel.className = "sub-panel";
    launchPanel.dataset.subpanel = "launch";

    const settingsPanel = document.createElement("div");
    settingsPanel.className = "sub-panel";
    settingsPanel.dataset.subpanel = "settings";

    const savesPanel = document.createElement("div");
    savesPanel.className = "sub-panel";
    savesPanel.dataset.subpanel = "saves";

    const installerPanel = document.createElement("div");
    installerPanel.className = "sub-panel";
    installerPanel.dataset.subpanel = "installer";

    panel.appendChild(launchPanel);
    panel.appendChild(settingsPanel);
    panel.appendChild(savesPanel);
    panel.appendChild(installerPanel);

    const allBtns = [btnLaunch, btnSettings, btnSaves, btnInstaller];
    const allPanels = [launchPanel, settingsPanel, savesPanel, installerPanel];

    function activateSub(idx) {
        allBtns.forEach((b, i) => b.classList.toggle("active", i === idx));
        allPanels.forEach((p, i) => p.classList.toggle("active", i === idx));
    }

    function updateTabVisibility() {
        const installed = currentGames[gameId]?.mod_installed;
        btnLaunch.classList.toggle("hidden", !installed);
        btnSettings.classList.toggle("hidden", !installed);
        btnSaves.classList.toggle("hidden", !installed);
    }

    btnLaunch.addEventListener("click", async () => {
        if (await promptUnsavedIfNeeded(gameId)) return;
        activateSub(0);
        renderLaunchPanel(gameId, launchPanel);
    });
    btnSettings.addEventListener("click", () => {
        activateSub(1);
        if (!settingsPanel.dataset.loaded) loadSettingsInto(gameId, settingsPanel);
    });
    btnSaves.addEventListener("click", async () => {
        if (await promptUnsavedIfNeeded(gameId)) return;
        activateSub(2);
        loadSavesUI(gameId, savesPanel);
    });
    btnInstaller.addEventListener("click", async () => {
        if (await promptUnsavedIfNeeded(gameId)) return;
        activateSub(3);
        loadModInstallerUI(gameId, installerPanel);
    });

    // Store a reference for post-install tab reveal
    panel._activateSub = activateSub;
    panel._updateTabVisibility = updateTabVisibility;
    panel._launchPanel = launchPanel;
    panel._settingsPanel = settingsPanel;

    // Deactivate other panels
    panels.querySelectorAll(".game-panel").forEach(p => p.classList.remove("active"));
    panels.appendChild(panel);

    // Set initial tab visibility and default sub-tab
    updateTabVisibility();
    if (game.mod_installed) {
        activateSub(0);
        renderLaunchPanel(gameId, launchPanel);
    } else {
        activateSub(3);
        await loadModInstallerUI(gameId, installerPanel);
    }
}

// ================================================================
// Launch panel
// ================================================================
function renderLaunchPanel(gameId, container) {
    const game = currentGames[gameId];
    container.innerHTML = "";

    const card = document.createElement("div");
    card.className = "launch-card";

    let launching = false;
    async function doLaunch() {
        if (launching || !game.launcher_exists) return;
        launching = true;
        icon.classList.add("launch-icon-active");
        subtitle.textContent = "Launching...";
        try {
            const res = await fetch(`/api/launch/${gameId}`, { method: "POST" });
            const d = await res.json();
            if (res.ok) {
                toast(d.message, "success");
                subtitle.textContent = "Launched!";
                setTimeout(() => {
                    launching = false;
                    icon.classList.remove("launch-icon-active");
                    subtitle.textContent = "Double-click to launch";
                }, 3000);
            } else {
                toast(d.error, "error");
                launching = false;
                icon.classList.remove("launch-icon-active");
                subtitle.textContent = "Double-click to launch";
            }
        } catch (e) {
            toast(e.message, "error");
            launching = false;
            icon.classList.remove("launch-icon-active");
            subtitle.textContent = "Double-click to launch";
        }
    }

    const icon = document.createElement("div");
    icon.className = "launch-icon";
    if (game.steam_app_id) {
        const img = document.createElement("img");
        img.className = "launch-game-img";
        img.src = `https://cdn.cloudflare.steamstatic.com/steam/apps/${game.steam_app_id}/library_600x900.jpg`;
        img.alt = game.name;
        img.draggable = false;
        icon.appendChild(img);
    } else {
        icon.innerHTML = "&#x1F3AE;";
    }
    icon.addEventListener("dblclick", doLaunch);
    card.appendChild(icon);

    const title = document.createElement("div");
    title.className = "launch-title";
    title.textContent = game.mod_name || `${game.name} Co-op`;
    card.appendChild(title);

    const subtitle = document.createElement("div");
    subtitle.className = "launch-subtitle";
    subtitle.textContent = "Double-click to launch";
    card.appendChild(subtitle);

    if (!game.launcher_exists) {
        const warn = document.createElement("div");
        warn.className = "launch-warning";
        warn.innerHTML = "&#x26A0; Launcher executable not found. Try reinstalling the mod.";
        card.appendChild(warn);
        subtitle.textContent = "Launcher not available";
    }

    container.appendChild(card);
}

// ================================================================
// Settings sub-panel (existing functionality)
// ================================================================
async function loadSettingsInto(gameId, container) {
    if (container.dataset.loaded) return; // already loaded
    try {
        const res = await fetch(`/api/settings/${gameId}`);
        if (!res.ok) {
            const err = await res.json();
            container.innerHTML = `<div class="landing" style="padding:2rem"><div class="landing-icon">&#x26A0;</div><p>${err.error || "Mod not installed yet. Use the Mod Installer tab first."}</p></div>`;
            return;
        }
        const data = await res.json();
        settingsCache[gameId] = data.sections;
        renderSettings(gameId, data, container);
        container.dataset.loaded = "1";
    } catch (err) {
        toast(`Failed to load settings: ${err.message}`, "error");
    }
}

function renderSettings(gameId, data, container) {
    container.innerHTML = "";

    // Store original and default values for change tracking
    originalValues[gameId] = {};
    defaultValues[gameId] = {};
    let hasDefaults = false;
    for (const section of data.sections) {
        for (const setting of section.settings) {
            originalValues[gameId][setting.key] = setting.value;
            if (setting.default !== undefined) {
                defaultValues[gameId][setting.key] = setting.default;
                hasDefaults = true;
            }
        }
    }
    dirtyGames.delete(gameId);

    const pathEl = document.createElement("div");
    pathEl.className = "config-path";
    pathEl.textContent = data.config_path;
    container.appendChild(pathEl);

    for (const section of data.sections) {
        const card = document.createElement("div");
        card.className = "section-card";

        const header = document.createElement("div");
        header.className = "section-header";
        header.textContent = section.name;
        card.appendChild(header);

        for (const setting of section.settings) {
            card.appendChild(buildSettingRow(gameId, setting));
        }
        container.appendChild(card);
    }

    const bar = document.createElement("div");
    bar.className = "save-bar";

    const changeIndicator = document.createElement("span");
    changeIndicator.className = "change-indicator hidden";
    changeIndicator.id = `changes-${gameId}`;
    changeIndicator.textContent = "Unsaved changes";
    bar.appendChild(changeIndicator);

    const undoBtn = document.createElement("button");
    undoBtn.className = "btn btn-undo hidden";
    undoBtn.id = `undo-${gameId}`;
    undoBtn.innerHTML = '<span class="btn-icon">&#x21A9;</span> Undo';
    undoBtn.addEventListener("click", () => discardChanges(gameId));
    bar.appendChild(undoBtn);

    const resetBtn = document.createElement("button");
    resetBtn.className = "btn btn-reset";
    resetBtn.innerHTML = '<span class="btn-icon">&#x1F504;</span> Reset to Defaults';
    resetBtn.addEventListener("click", () => resetToDefaults(gameId));
    if (!hasDefaults) resetBtn.style.display = "none";
    bar.appendChild(resetBtn);

    const saveBtn = document.createElement("button");
    saveBtn.className = "btn btn-success";
    saveBtn.innerHTML = '<span class="btn-icon">&#x1F4BE;</span> Save Settings';
    saveBtn.addEventListener("click", () => saveSettings(gameId));
    bar.appendChild(saveBtn);
    container.appendChild(bar);
}

function buildSettingRow(gameId, setting) {
    const row = document.createElement("div");
    row.className = "setting-row";

    const info = document.createElement("div");
    info.className = "setting-info";
    const keyEl = document.createElement("div");
    keyEl.className = "setting-key";
    keyEl.textContent = prettifyKey(setting.key);
    info.appendChild(keyEl);
    if (setting.description) {
        const desc = document.createElement("div");
        desc.className = "setting-desc";
        desc.textContent = setting.description;
        info.appendChild(desc);
    }
    row.appendChild(info);

    const ctrl = document.createElement("div");
    ctrl.className = "setting-control";
    let input;
    if (setting.type === "select" && setting.options) {
        input = document.createElement("select");
        for (const opt of setting.options) {
            const o = document.createElement("option");
            o.value = opt.value;
            o.textContent = `${opt.value} — ${opt.label}`;
            if (opt.value === setting.value) o.selected = true;
            input.appendChild(o);
        }
    } else if (setting.type === "number") {
        input = document.createElement("input");
        input.type = "number";
        input.value = setting.value;
        if (setting.min != null) input.min = setting.min;
        if (setting.max != null) input.max = setting.max;
    } else {
        input = document.createElement("input");
        input.type = "text";
        input.value = setting.value;
    }
    input.dataset.game = gameId;
    input.dataset.key = setting.key;
    input.dataset.original = setting.value;
    input.addEventListener("input", () => onSettingChanged(gameId, input));
    input.addEventListener("change", () => onSettingChanged(gameId, input));
    ctrl.appendChild(input);
    row.appendChild(ctrl);
    return row;
}

function onSettingChanged(gameId, input) {
    const row = input.closest(".setting-row");
    const changed = input.value !== input.dataset.original;
    row.classList.toggle("setting-changed", changed);
    // Recalculate dirty state for this game
    const allInputs = panels.querySelectorAll(`.game-panel[data-game="${gameId}"] [data-key]`);
    let anyDirty = false;
    allInputs.forEach(el => {
        if (el.value !== el.dataset.original) anyDirty = true;
    });
    if (anyDirty) dirtyGames.add(gameId); else dirtyGames.delete(gameId);
    const indicator = document.getElementById(`changes-${gameId}`);
    if (indicator) indicator.classList.toggle("hidden", !anyDirty);
    const undoBtn = document.getElementById(`undo-${gameId}`);
    if (undoBtn) undoBtn.classList.toggle("hidden", !anyDirty);
}

function getChangedSettings(gameId) {
    const changes = [];
    const inputs = panels.querySelectorAll(`.game-panel[data-game="${gameId}"] [data-key]`);
    inputs.forEach(el => {
        if (el.value !== el.dataset.original) {
            changes.push({ key: el.dataset.key, from: el.dataset.original, to: el.value });
        }
    });
    return changes;
}

function discardChanges(gameId) {
    const inputs = panels.querySelectorAll(`.game-panel[data-game="${gameId}"] [data-key]`);
    inputs.forEach(el => {
        el.value = el.dataset.original;
        el.closest(".setting-row").classList.remove("setting-changed");
    });
    dirtyGames.delete(gameId);
    const indicator = document.getElementById(`changes-${gameId}`);
    if (indicator) indicator.classList.add("hidden");
    const undoBtn = document.getElementById(`undo-${gameId}`);
    if (undoBtn) undoBtn.classList.add("hidden");
}

async function resetToDefaults(gameId) {
    const defs = defaultValues[gameId];
    if (!defs || Object.keys(defs).length === 0) {
        toast("No default values available for this game", "info");
        return;
    }
    // Build a preview of what will change
    const inputs = panels.querySelectorAll(`.game-panel[data-game="${gameId}"] [data-key]`);
    const changes = [];
    inputs.forEach(el => {
        const defVal = defs[el.dataset.key];
        if (defVal !== undefined && el.value !== defVal) {
            changes.push({ key: el.dataset.key, from: el.value, to: defVal });
        }
    });
    if (changes.length === 0) {
        toast("All settings are already at their default values", "info");
        return;
    }
    const lines = changes.map(c =>
        `<tr><td>${prettifyKey(c.key)}</td><td class="val-from">${c.from}</td><td class="val-to">${c.to}</td></tr>`
    ).join("");
    const body = `This will reset ${changes.length} setting(s) to mod defaults:<br><table class="change-table"><thead><tr><th>Setting</th><th>Current</th><th>Default</th></tr></thead><tbody>${lines}</tbody></table><br><em>Changes are not saved yet — you can still undo or edit before saving.</em>`;
    const ok = await confirm("Reset to Defaults?", body);
    if (!ok) return;
    // Apply defaults to inputs (but don't save to file yet)
    inputs.forEach(el => {
        const defVal = defs[el.dataset.key];
        if (defVal !== undefined) {
            el.value = defVal;
            onSettingChanged(gameId, el);
        }
    });
    toast(`Reset ${changes.length} setting(s) to defaults — remember to Save`, "info");
}

async function promptUnsavedIfNeeded(gameId) {
    if (!dirtyGames.has(gameId)) return false;
    const changes = getChangedSettings(gameId);
    if (changes.length === 0) return false;
    const lines = changes.map(c =>
        `<tr><td>${prettifyKey(c.key)}</td><td class="val-from">${c.from}</td><td class="val-to">${c.to}</td></tr>`
    ).join("");
    const body = `You have unsaved changes:<br><table class="change-table"><thead><tr><th>Setting</th><th>From</th><th>To</th></tr></thead><tbody>${lines}</tbody></table><br>Discard these changes?`;
    const ok = await confirm("Unsaved Changes", body);
    if (ok) { discardChanges(gameId); return false; }
    return true; // user cancelled, stay on settings
}

async function saveSettings(gameId) {
    const changes = getChangedSettings(gameId);
    if (changes.length === 0) {
        toast("No changes to save", "info");
        return;
    }

    // Build a change summary for confirmation
    const changeLines = changes.map(c =>
        `<tr><td>${prettifyKey(c.key)}</td><td class="val-from">${c.from}</td><td class="val-to">${c.to}</td></tr>`
    ).join("");
    const body = `<table class="change-table"><thead><tr><th>Setting</th><th>From</th><th>To</th></tr></thead><tbody>${changeLines}</tbody></table>`;

    const ok = await confirm("Save Settings?", body);
    if (!ok) return;

    const inputs = panels.querySelectorAll(
        `.game-panel[data-game="${gameId}"] [data-key]`
    );
    const payload = {};
    inputs.forEach(el => { payload[el.dataset.key] = el.value; });

    try {
        const res = await fetch(`/api/settings/${gameId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (res.ok) {
            toast(data.message || "Saved!", "success");
            // Update originals so fields are no longer marked dirty
            inputs.forEach(el => {
                el.dataset.original = el.value;
                el.closest(".setting-row").classList.remove("setting-changed");
            });
            dirtyGames.delete(gameId);
            const indicator = document.getElementById(`changes-${gameId}`);
            if (indicator) indicator.classList.add("hidden");
            const undoBtn = document.getElementById(`undo-${gameId}`);
            if (undoBtn) undoBtn.classList.add("hidden");
        } else {
            toast(data.error || "Save failed", "error");
        }
    } catch (err) {
        toast("Save failed: " + err.message, "error");
    }
}

// ================================================================
// Saves sub-panel (NEW — save management)
// ================================================================
async function loadSavesUI(gameId, container) {
    container.innerHTML = '<div class="landing" style="padding:2rem"><div class="spinner"></div><p>Loading save info...</p></div>';

    try {
        const res = await fetch(`/api/saves/${gameId}?_=${Date.now()}`);
        if (!res.ok) {
            const err = await res.json();
            container.innerHTML = `<div class="landing" style="padding:2rem"><div class="landing-icon">&#x26A0;</div><p>${err.error || "Failed to load saves"}</p></div>`;
            return;
        }
        const data = await res.json();
        renderSavesUI(gameId, data, container);
    } catch (err) {
        container.innerHTML = `<div class="landing" style="padding:2rem"><div class="landing-icon">&#x26A0;</div><p>${err.message}</p></div>`;
    }
}

function renderSavesUI(gameId, data, container) {
    container.innerHTML = "";

    // Save directory path
    const dirInfo = document.createElement("div");
    dirInfo.className = "save-dir-info";
    dirInfo.textContent = `Save location: ${data.save_dir}`;
    container.appendChild(dirInfo);

    // ── Transfer section ──
    const transferTitle = document.createElement("div");
    transferTitle.className = "save-section-title";
    transferTitle.textContent = "Transfer Saves";
    container.appendChild(transferTitle);

    const transferRow = document.createElement("div");
    transferRow.className = "transfer-row";

    transferRow.appendChild(buildTransferCard(
        "Base Game → Co-op",
        `Copy your base game saves (${data.base_ext}) to co-op format (${data.coop_ext}). Current co-op saves are backed up automatically.`,
        "btn btn-blue", "base_to_coop", gameId, container
    ));
    transferRow.appendChild(buildTransferCard(
        "Co-op → Base Game",
        `Copy your co-op saves (${data.coop_ext}) back to base game format (${data.base_ext}). Current base saves are backed up automatically.`,
        "btn btn-blue", "coop_to_base", gameId, container,
        `<div style="margin-top:.6rem;padding:.6rem .8rem;background:#e74c3c22;border:1px solid #e74c3c66;border-radius:6px;font-size:.85rem">` +
        `<strong>⚠️ Ban Risk:</strong> Using co-op saves on official FromSoftware online servers may get your account flagged or banned. ` +
        `Co-op mod saves can contain data the anti-cheat considers illegitimate. <strong>Proceed at your own risk.</strong></div>`
    ));
    container.appendChild(transferRow);

    // ── Current save files ──
    const filesTitle = document.createElement("div");
    filesTitle.className = "save-section-title";
    filesTitle.textContent = "Current Save Files";
    container.appendChild(filesTitle);

    const filesRow = document.createElement("div");
    filesRow.className = "save-files-row";

    filesRow.appendChild(buildFileGroup(`Base Game (${data.base_ext})`, data.base_files));
    filesRow.appendChild(buildFileGroup(`Co-op (${data.coop_ext})`, data.coop_files));
    container.appendChild(filesRow);

    // ── Backups section ──
    const backupHeader = document.createElement("div");
    backupHeader.className = "backup-header";

    const backupTitle = document.createElement("div");
    backupTitle.className = "save-section-title";
    backupTitle.style.margin = "0";
    backupTitle.textContent = "Backups";
    backupHeader.appendChild(backupTitle);

    const backupBtn = document.createElement("button");
    backupBtn.className = "btn btn-success btn-sm";
    backupBtn.innerHTML = '<span class="btn-icon">&#x1F4BE;</span> Create Backup';
    backupBtn.addEventListener("click", async () => {
        const ok = await confirm("Create Backup", "Back up all current save files (base + co-op) with a timestamp?");
        if (!ok) return;
        try {
            const res = await fetch(`/api/saves/${gameId}/backup`, { method: "POST" });
            const d = await res.json();
            if (res.ok) { toast(d.message, "success"); loadSavesUI(gameId, container); }
            else toast(d.error, "error");
        } catch (e) { toast(e.message, "error"); }
    });
    backupHeader.appendChild(backupBtn);
    container.appendChild(backupHeader);

    const backupList = document.createElement("div");
    backupList.className = "backup-list";

    if (data.backups.length === 0) {
        const none = document.createElement("div");
        none.className = "backup-none";
        none.textContent = "No backups yet. Create one to protect your saves.";
        backupList.appendChild(none);
    } else {
        for (const bk of data.backups) {
            backupList.appendChild(buildBackupEntry(gameId, bk, container));
        }
    }
    container.appendChild(backupList);
}

// ── Transfer card builder ──
function buildTransferCard(title, description, btnClass, direction, gameId, refreshContainer, extraWarningHtml) {
    const card = document.createElement("div");
    card.className = "transfer-card";

    const h3 = document.createElement("h3");
    h3.textContent = title;
    card.appendChild(h3);

    const p = document.createElement("p");
    p.textContent = description;
    card.appendChild(p);

    if (extraWarningHtml) {
        const warn = document.createElement("div");
        warn.innerHTML = extraWarningHtml;
        card.appendChild(warn);
    }

    const btn = document.createElement("button");
    btn.className = btnClass;
    btn.textContent = "Transfer";
    btn.addEventListener("click", async () => {
        const warningBlock = extraWarningHtml ? `<br>${extraWarningHtml}` : '';
        const ok = await confirm("Transfer Saves", `<strong>${title}</strong><br><br>${description}<br><br>This will overwrite the destination saves. A backup of them will be created first.${warningBlock}`);
        if (!ok) return;
        try {
            const res = await fetch(`/api/saves/${gameId}/transfer`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ direction }),
            });
            const d = await res.json();
            if (res.ok) { toast(d.message, "success"); loadSavesUI(gameId, refreshContainer); }
            else toast(d.error, "error");
        } catch (e) { toast(e.message, "error"); }
    });
    card.appendChild(btn);
    return card;
}

// ── File group builder ──
function buildFileGroup(title, files) {
    const group = document.createElement("div");
    group.className = "file-group";

    const titleEl = document.createElement("div");
    titleEl.className = "file-group-title";
    titleEl.textContent = title;
    group.appendChild(titleEl);

    if (files.length === 0) {
        const none = document.createElement("div");
        none.className = "file-none";
        none.textContent = "No files found";
        group.appendChild(none);
    } else {
        for (const f of files) {
            const card = document.createElement("div");
            card.className = "file-card";
            card.innerHTML = `
                <div class="file-name">${f.name}</div>
                <div class="file-meta">${formatSize(f.size)} &middot; ${formatDate(f.modified)}</div>
            `;
            group.appendChild(card);
        }
    }
    return group;
}

// ── Backup entry builder ──
function buildBackupEntry(gameId, bk, refreshContainer) {
    const entry = document.createElement("div");
    entry.className = "backup-entry";

    const left = document.createElement("div");
    const ts = document.createElement("div");
    ts.className = "backup-ts";
    ts.textContent = bk.timestamp.replace(/_/g, " ");
    left.appendChild(ts);
    const counts = document.createElement("div");
    counts.className = "backup-counts";
    counts.textContent = `Base: ${bk.base_count} file(s) · Co-op: ${bk.coop_count} file(s)`;
    left.appendChild(counts);
    entry.appendChild(left);

    const actions = document.createElement("div");
    actions.className = "backup-actions";

    // Restore label
    const restoreLabel = document.createElement("span");
    restoreLabel.className = "backup-actions-label";
    restoreLabel.textContent = "Restore to:";
    actions.appendChild(restoreLabel);

    // Restore → Base
    const restBase = document.createElement("button");
    restBase.className = "btn btn-blue btn-sm";
    restBase.innerHTML = "&#x1F4E5; Base Game";
    restBase.title = "Restore this backup to base game saves";
    restBase.addEventListener("click", async () => {
        const ok = await confirm("Restore Backup → Base Game",
            `This will <strong>restore</strong> backup <strong>${bk.timestamp}</strong> to your <strong>base game</strong> saves.<br><br>Your current base saves will be safely backed up first before being overwritten.`);
        if (!ok) return;
        await doRestore(gameId, bk.timestamp, "base", refreshContainer);
    });
    actions.appendChild(restBase);

    // Restore → Coop
    const restCoop = document.createElement("button");
    restCoop.className = "btn btn-warn btn-sm";
    restCoop.innerHTML = "&#x1F4E5; Co-op";
    restCoop.title = "Restore this backup to co-op saves";
    restCoop.addEventListener("click", async () => {
        const ok = await confirm("Restore Backup → Co-op",
            `This will <strong>restore</strong> backup <strong>${bk.timestamp}</strong> to your <strong>co-op</strong> saves.<br><br>Your current co-op saves will be safely backed up first before being overwritten.`);
        if (!ok) return;
        await doRestore(gameId, bk.timestamp, "coop", refreshContainer);
    });
    actions.appendChild(restCoop);

    // Separator
    const sep = document.createElement("span");
    sep.className = "backup-actions-sep";
    actions.appendChild(sep);

    // Delete
    const del = document.createElement("button");
    del.className = "btn btn-danger btn-sm";
    del.innerHTML = "&#x1F5D1; Delete";
    del.addEventListener("click", async () => {
        const ok = await confirm("Delete Backup",
            `Permanently delete backup <strong>${bk.timestamp}</strong>?<br>This cannot be undone.`);
        if (!ok) return;
        try {
            const res = await fetch(`/api/saves/${gameId}/backup/${bk.timestamp}`, { method: "DELETE" });
            const d = await res.json();
            if (res.ok) { toast(d.message, "success"); loadSavesUI(gameId, refreshContainer); }
            else toast(d.error, "error");
        } catch(e) { toast(e.message, "error"); }
    });
    actions.appendChild(del);

    entry.appendChild(actions);
    return entry;
}

async function doRestore(gameId, timestamp, destType, refreshContainer) {
    try {
        const res = await fetch(`/api/saves/${gameId}/restore`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ timestamp, dest_type: destType }),
        });
        const d = await res.json();
        if (res.ok) { toast(d.message, "success"); loadSavesUI(gameId, refreshContainer); }
        else toast(d.error, "error");
    } catch (e) { toast(e.message, "error"); }
}

// ================================================================
// Mod Installer sub-panel
// ================================================================
async function loadModInstallerUI(gameId, container) {
    container.innerHTML = '<div class="landing" style="padding:2rem"><div class="spinner"></div><p>Checking mod status...</p></div>';

    try {
        const res = await fetch(`/api/mod/${gameId}/status?_=${Date.now()}`);
        if (!res.ok) {
            const err = await res.json();
            container.innerHTML = `<div class="landing" style="padding:2rem"><div class="landing-icon">&#x26A0;</div><p>${err.error}</p></div>`;
            return;
        }
        const data = await res.json();
        renderModInstallerUI(gameId, data, container);
    } catch (err) {
        container.innerHTML = `<div class="landing" style="padding:2rem"><div class="landing-icon">&#x26A0;</div><p>${err.message}</p></div>`;
    }
}

function renderModInstallerUI(gameId, data, container) {
    container.innerHTML = "";

    // ── Status badge ──
    const statusBar = document.createElement("div");
    statusBar.className = `installer-status-bar ${data.mod_installed ? "mod-yes" : "mod-no"}`;
    statusBar.innerHTML = data.mod_installed
        ? '&#x2714; Mod installed'
        : '&#x2716; Mod not installed';
    container.appendChild(statusBar);

    // ── Nexus Mods download link ──
    const nexusCard = document.createElement("div");
    nexusCard.className = "section-card installer-nexus-card";

    const nexusHeader = document.createElement("div");
    nexusHeader.className = "section-header";
    nexusHeader.textContent = data.mod_name;
    nexusCard.appendChild(nexusHeader);

    const nexusBody = document.createElement("div");
    nexusBody.className = "installer-step-body";
    nexusBody.innerHTML = `
        <p>Download from Nexus Mods using the link below. You'll need a free account &mdash; use the <strong>"Manual"</strong> download option.</p>
        <a href="${data.nexus_url}" target="_blank" class="nexus-link">${data.nexus_url}</a>
    `;
    nexusCard.appendChild(nexusBody);
    container.appendChild(nexusCard);

    // ── Install from Downloads ──
    const installCard = document.createElement("div");
    installCard.className = "section-card";

    const installHeader = document.createElement("div");
    installHeader.className = "section-header";
    installHeader.textContent = "Install from Downloads";
    installCard.appendChild(installHeader);

    const installBody = document.createElement("div");
    installBody.className = "installer-step-body";

    const targetInfo = document.createElement("div");
    targetInfo.className = "installer-detail";
    targetInfo.innerHTML = `<span class="detail-label">Extracts to:</span> <span class="detail-value">${data.extract_target}</span>`;
    installBody.appendChild(targetInfo);

    if (data.available_zips.length === 0) {
        const noZips = document.createElement("p");
        noZips.className = "installer-note";
        noZips.textContent = "No matching mod archives found in your Downloads folder. Download the mod above, then click Refresh.";
        installBody.appendChild(noZips);
    } else {
        const hint = document.createElement("p");
        hint.style.marginBottom = ".6rem";
        hint.innerHTML = `Found in <code>${data.downloads_dir}</code>:`;
        installBody.appendChild(hint);

        const zipList = document.createElement("div");
        zipList.className = "zip-list";

        for (const zip of data.available_zips) {
            const zipEntry = document.createElement("div");
            zipEntry.className = "zip-entry";

            const zipInfo = document.createElement("div");
            zipInfo.className = "zip-info";
            zipInfo.innerHTML = `
                <div class="zip-name">${zip.name}</div>
                <div class="zip-meta">${formatSize(zip.size)} &middot; ${formatDate(zip.modified)}</div>
            `;
            zipEntry.appendChild(zipInfo);

            const installBtn = document.createElement("button");
            installBtn.className = "btn btn-success";
            installBtn.innerHTML = "&#x1F4E6; Install";
            installBtn.addEventListener("click", async () => {
                const ok = await confirm("Install Mod",
                    `Extract <strong>${zip.name}</strong> into:<br><code>${data.extract_target}</code><br><br>This will overwrite any existing mod files.`);
                if (!ok) return;
                installBtn.disabled = true;
                installBtn.textContent = "Installing...";
                try {
                    const res = await fetch(`/api/mod/${gameId}/install`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ zip_name: zip.name }),
                    });
                    const d = await res.json();
                    if (res.ok) {
                        toast(d.message, "success");
                        if (currentGames[gameId]) {
                            currentGames[gameId].mod_installed = d.mod_installed;
                            currentGames[gameId].launcher_exists = d.launcher_exists;
                        }
                        delete settingsCache[gameId];
                        const gamePanel = panels.querySelector(`.game-panel[data-game="${gameId}"]`);
                        const sp = gamePanel?.querySelector('[data-subpanel="settings"]');
                        if (sp) delete sp.dataset.loaded;
                        // Reveal hidden tabs and switch to Launch
                        if (d.mod_installed && gamePanel) {
                            if (gamePanel._updateTabVisibility) gamePanel._updateTabVisibility();
                            if (gamePanel._activateSub) {
                                gamePanel._activateSub(0);
                                if (gamePanel._launchPanel) renderLaunchPanel(gameId, gamePanel._launchPanel);
                            }
                        } else {
                            loadModInstallerUI(gameId, container);
                        }

                        // Prompt to clean up the zip from Downloads
                        if (d.zip_name) {
                            const cleanup = await confirm("Install Successful!",
                                `<strong>${d.zip_name}</strong> was installed successfully.<br><br>` +
                                `Would you like to delete the zip file from your Downloads folder to free up space?`);
                            if (cleanup) {
                                try {
                                    const cr = await fetch(`/api/mod/${gameId}/cleanup`, {
                                        method: "POST",
                                        headers: { "Content-Type": "application/json" },
                                        body: JSON.stringify({ zip_name: d.zip_name }),
                                    });
                                    const cd = await cr.json();
                                    if (cr.ok) {
                                        toast(cd.message, "success");
                                    } else {
                                        toast(cd.error, "error");
                                    }
                                } catch (ce) {
                                    toast(ce.message, "error");
                                }
                            }
                        }
                    } else {
                        toast(d.error, "error");
                        installBtn.disabled = false;
                        installBtn.innerHTML = "&#x1F4E6; Install";
                    }
                } catch (e) {
                    toast(e.message, "error");
                    installBtn.disabled = false;
                    installBtn.innerHTML = "&#x1F4E6; Install";
                }
            });

            const deleteBtn = document.createElement("button");
            deleteBtn.className = "btn btn-danger-sm";
            deleteBtn.innerHTML = "&#x1F5D1; Delete";
            deleteBtn.title = `Delete ${zip.name} from Downloads`;
            deleteBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const ok = await confirm("Delete Download",
                    `Are you sure you want to delete <strong>${zip.name}</strong> from your Downloads folder?<br><br>` +
                    `<span style="color:var(--text-muted)">${formatSize(zip.size)}</span>`);
                if (!ok) return;
                deleteBtn.disabled = true;
                deleteBtn.textContent = "Deleting...";
                try {
                    const res = await fetch(`/api/mod/${gameId}/cleanup`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ zip_name: zip.name }),
                    });
                    const d = await res.json();
                    if (res.ok) {
                        toast(d.message, "success");
                        zipEntry.style.transition = "opacity .3s";
                        zipEntry.style.opacity = "0";
                        setTimeout(() => zipEntry.remove(), 300);
                    } else {
                        toast(d.error, "error");
                        deleteBtn.disabled = false;
                        deleteBtn.innerHTML = "&#x1F5D1; Delete";
                    }
                } catch (err) {
                    toast(err.message, "error");
                    deleteBtn.disabled = false;
                    deleteBtn.innerHTML = "&#x1F5D1; Delete";
                }
            });

            const btnGroup = document.createElement("div");
            btnGroup.className = "zip-actions";
            btnGroup.appendChild(installBtn);
            btnGroup.appendChild(deleteBtn);
            zipEntry.appendChild(btnGroup);
            zipList.appendChild(zipEntry);
        }
        installBody.appendChild(zipList);
    }

    const refreshBtn = document.createElement("button");
    refreshBtn.className = "btn btn-muted btn-sm";
    refreshBtn.innerHTML = "&#x1F504; Refresh";
    refreshBtn.style.marginTop = ".8rem";
    refreshBtn.addEventListener("click", () => loadModInstallerUI(gameId, container));
    installBody.appendChild(refreshBtn);

    installCard.appendChild(installBody);
    container.appendChild(installCard);

    // ── Usage info ──
    const infoCard = document.createElement("div");
    infoCard.className = "section-card";

    const infoHeader = document.createElement("div");
    infoHeader.className = "section-header";
    infoHeader.textContent = "Usage";
    infoCard.appendChild(infoHeader);

    const infoBody = document.createElement("div");
    infoBody.className = "installer-step-body";
    infoBody.innerHTML = `
        <ol class="installer-steps-list">
            <li>Download the mod zip from the link above</li>
            <li>Click <strong>Install</strong> to extract it into your game folder</li>
            <li>Go to <strong>Mod Settings</strong> to configure options</li>
            <li>Launch using the co-op launcher in your game folder</li>
        </ol>
        <p class="installer-note">To play without the mod, just launch the game normally. To remove it fully, delete the mod files from your game folder.</p>
    `;
    infoCard.appendChild(infoBody);
    container.appendChild(infoCard);
}

// ─── Unsaved changes guard ───────────────────────────────────
window.addEventListener("beforeunload", (e) => {
    if (dirtyGames.size > 0) {
        e.preventDefault();
        e.returnValue = "";
    }
});

// ─── Boot ────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", loadConfig);
