-- ~/.config/hypr/hyprland.lua — summer-day-and-night, Lua version (Hyprland 0.56+)
-- Saving this file reloads it. Wiki: https://wiki.hypr.land/configuring/

-- ===== Pick your theme: "summer-night" or "summer-day" =====
local themeName = "summer-night"
local theme     = require("themes." .. themeName)

local terminal    = "kitty"
local fileManager = "nemo"
local mainMod     = "SUPER"

---------------- Monitors ----------------
-- Any screen: best mode, placed automatically to the right.
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })
-- Your own layout: `hyprctl monitors` shows each screen's name and description.
-- Match a screen by its description so it keeps its place on any port, e.g.:
-- hl.monitor({ output = "desc:Dell Inc. DELL U2720Q ABC123", mode = "preferred", position = "0x0", scale = 1.5 })
-- hl.monitor({ output = "desc:LG Electronics 27GL850 XYZ", mode = "preferred", position = "0x0", scale = 1, transform = 1 })  -- vertical
-- hl.monitor({ output = "eDP-1", mode = "preferred", position = "2560x360", scale = 1 })

---------------- Environment ----------------
hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")
hl.env("QT_QPA_PLATFORM", "wayland;xcb")
hl.env("MOZ_ENABLE_WAYLAND", "1")
hl.env("GTK_THEME", theme.gtk)
-- NVIDIA only:
-- hl.env("LIBVA_DRIVER_NAME", "nvidia")
-- hl.env("__GLX_VENDOR_LIBRARY_NAME", "nvidia")

---------------- Autostart ----------------
local function startBarAndWallpaper()
    hl.exec_cmd("pkill swaybg; swaybg -i ~/.config/hypr/wallpapers/" .. themeName .. ".png -m fill")
    hl.exec_cmd("pkill waybar; waybar -c ~/.config/waybar/" .. theme.colors .. "/config -s ~/.config/waybar/" .. theme.colors .. "/style.css")
    -- sound + quick settings popups wait hidden in the background, so they open instantly
    hl.exec_cmd("~/.config/waybar/scripts/popup.sh --restart " .. theme.colors)
end

hl.on("hyprland.start", function()
    hl.exec_cmd("dbus-update-activation-environment --systemd --all && systemctl --user start hyprland-session.target")
    -- password prompts for apps (the path differs per distro)
    hl.exec_cmd("for a in /usr/libexec/polkit-mate-authentication-agent-1 /usr/lib/mate-polkit/polkit-mate-authentication-agent-1 /usr/lib/x86_64-linux-gnu/polkit-mate/polkit-mate-authentication-agent-1; do [ -x \"$a\" ] && exec \"$a\"; done")
    hl.exec_cmd("wl-paste --type text --watch cliphist store")
    hl.exec_cmd("wl-paste --type image --watch cliphist store")
    hl.exec_cmd("swaync")
    startBarAndWallpaper()
end)
-- restart bar + wallpaper when you change the theme and save
hl.on("config.reloaded", startBarAndWallpaper)

---------------- Look and feel ----------------
hl.config({
    general = {
        gaps_in = 10,
        gaps_out = 20,
        border_size = 4,
        col = {
            active_border   = theme.fg,
            inactive_border = theme.bg5,
        },
        layout = "dwindle",
        resize_on_border = true,
    },
    decoration = {
        rounding = 10,
        blur = { enabled = false },
        shadow = {
            enabled = true,
            range = 0,
            render_power = 4,
            color = theme.shadow,
            color_inactive = theme.shadow_inactive,
            offset = "0 10",
        },
    },
    animations = { enabled = true },
    group = {
        col = {
            border_active   = theme.bg5,
            border_inactive = theme.fg,
        },
    },
    dwindle = { preserve_split = true },
    master  = { new_status = "master" },
    misc = {
        focus_on_activate = true,
        disable_hyprland_logo = true,
        disable_splash_rendering = true,
    },
    cursor = { inactive_timeout = 0 },
    binds  = { workspace_back_and_forth = true },
})

hl.curve("slow",     { type = "bezier", points = { {0, 0.85},   {0.3, 1}   } })
hl.curve("overshot", { type = "bezier", points = { {0.7, 0.6},  {0.1, 1.1} } })
hl.curve("bounce",   { type = "bezier", points = { {1, 1.6},    {0.1, 0.85} } })
hl.animation({ leaf = "windows",     enabled = true, speed = 5,  bezier = "bounce",   style = "popin" })
hl.animation({ leaf = "windowsIn",   enabled = true, speed = 5,  bezier = "slow",     style = "popin" })
hl.animation({ leaf = "windowsMove", enabled = true, speed = 5,  bezier = "default" })
hl.animation({ leaf = "border",      enabled = true, speed = 20, bezier = "default" })
hl.animation({ leaf = "fade",        enabled = true, speed = 5,  bezier = "overshot" })
hl.animation({ leaf = "workspaces",  enabled = true, speed = 6,  bezier = "overshot", style = "slidevert" })
-- popups, menus, bar and notifications: a quick plain fade (they used the slow window
-- fade above, so every popup took half a second to appear)
hl.animation({ leaf = "layers",      enabled = true, speed = 1.5, bezier = "default", style = "fade" })
hl.animation({ leaf = "fadeLayers",  enabled = true, speed = 1.5, bezier = "default" })

---------------- Input ----------------
hl.config({
    input = {
        kb_layout  = "us,ir",
        kb_variant = "",
        numlock_by_default = true,
        follow_mouse = 1,
        sensitivity = 0,
        touchpad = { natural_scroll = true },
    },
})
hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })

---------------- Window rules ----------------
hl.window_rule({ name = "pavucontrol", match = { class = "^(org.pulseaudio.pavucontrol|pavucontrol)$" }, float = true, center = true, size = "600 800" })
hl.window_rule({ name = "blueman",     match = { class = "^(blueman-manager)$" }, float = true })
hl.window_rule({ name = "calculator",  match = { class = "^(org.gnome.Calculator)$" }, float = true, size = "490 600" })
hl.window_rule({ name = "viewers",     match = { class = "^(eog|org.gnome.eog|vlc|imv)$" }, float = true, center = true })
hl.window_rule({ name = "file-dialogs",match = { title = "^(Confirm to replace files|File Operation Progress)$" }, float = true })

---------------- Keybinds ----------------
local function bind(keys, action, opts) hl.bind(keys, action, opts) end
local exec = hl.dsp.exec_cmd

-- apps & menus
bind(mainMod .. " + Return", exec(terminal))
bind(mainMod .. " + E",      exec(fileManager))
-- launcher: stays running hidden, opens instantly; most-used apps first
bind(mainMod .. " + D",      exec("~/.config/waybar/scripts/popup.sh launcher " .. theme.colors))
bind(mainMod .. " + B",      exec("~/.config/waybar/scripts/popup.sh power-popup " .. theme.colors))
bind(mainMod .. " + C",      exec("~/.config/waybar/scripts/popup.sh calculator " .. theme.colors))
bind(mainMod .. " + V",      exec("~/.config/waybar/scripts/popup.sh clipboard " .. theme.colors))
bind(mainMod .. " + period", exec("~/.config/waybar/scripts/popup.sh emoji-picker " .. theme.colors))

-- session
bind(mainMod .. " + M",         hl.dsp.exit())
bind(mainMod .. " + SHIFT + R", exec("hyprctl reload && notify-send 'Hyprland reloaded'"))
-- switch the language on every keyboard together (Alt+Shift in either order, or SUPER+Space)
local switchLayout = exec("~/.config/hypr/scripts/switch-layout.sh")
bind(mainMod .. " + SPACE",     switchLayout)
bind("ALT + Shift_L",           switchLayout)
bind("SHIFT + Alt_L",           switchLayout)

-- windows
bind(mainMod .. " + Q",             hl.dsp.window.close())
bind(mainMod .. " + F",             hl.dsp.window.fullscreen())
bind(mainMod .. " + SHIFT + F",     hl.dsp.window.fullscreen({ mode = "maximized" }))
bind(mainMod .. " + SHIFT + SPACE", hl.dsp.window.float({ action = "toggle" }))
bind(mainMod .. " + P",             hl.dsp.window.pseudo())
bind(mainMod .. " + J",             hl.dsp.layout("togglesplit"))
bind(mainMod .. " + G",             hl.dsp.group.toggle())
bind(mainMod .. " + Tab",           hl.dsp.group.next())
bind("ALT + Tab",                   hl.dsp.focus({ last = true }))
bind(mainMod .. " + H",             exec("sh ~/.config/hypr/scripts/toggle-gaps.sh"))

-- "minimize" = send to hidden scratchpad; SUPER+minus shows/hides it
bind(mainMod .. " + A",     hl.dsp.window.move({ workspace = "special:magic", follow = false }))
bind(mainMod .. " + minus", hl.dsp.workspace.toggle_special("magic"))

-- focus / move with arrows
for _, dir in ipairs({ "left", "right" }) do
    bind(mainMod .. " + SHIFT + " .. dir, hl.dsp.window.move({ direction = dir }))
end
-- One desk across all monitors: 10 desks, and every monitor switches together.
-- Hyprland keeps one workspace per monitor, so every screen owns a fixed block of
-- 10 workspaces: laptop 1-10, first external 11-20, next 21-30; waybar labels them all "N".
-- The block belongs to the screen itself (not to its position or the order it was
-- plugged in), so the layout survives screens sleeping, lock, lid and replugging.
-- Keys, bar clicks and touchpad swipes all stay in sync.
local DESKS = 10
-- Pin your external screens to a block (their description from `hyprctl monitors`);
-- others get the next free block in the order they appear.
local HOME_SLOTS = {
    -- ["Dell Inc. DELL U2720Q ABC123"] = 1,
    -- ["LG Electronics 27GL850 XYZ"]   = 2,
}
local ORIGINS_FILE = (os.getenv("XDG_RUNTIME_DIR") or "/tmp") .. "/hypr-desk-origins"

local function isInternal(m) return m.name:match("^eDP") or m.name:match("^LVDS") or m.name:match("^DSI") end
-- Hyprland's stand-in output while every real screen is off
local function isReal(m) return not (m.name:match("^FALLBACK") or m.name:match("^HEADLESS")) end

-- any other screen gets the next free block (remembered until the config reloads)
local extraSlots = {}
local function slotOf(m)
    if isInternal(m) then return 0 end
    if HOME_SLOTS[m.description] then return HOME_SLOTS[m.description] end
    local key = m.description ~= "" and m.description or m.name
    if not extraSlots[key] then
        local top = 0
        for _, s in pairs(HOME_SLOTS) do top = math.max(top, s) end
        for _, s in pairs(extraSlots) do top = math.max(top, s) end
        extraSlots[key] = top + 1
    end
    return extraSlots[key]
end

-- real screens from left to right, and monitor name -> slot
local function monitorSlots()
    local mons = {}
    for _, m in ipairs(hl.get_monitors()) do
        if isReal(m) then mons[#mons + 1] = m end
    end
    table.sort(mons, function(a, b)
        if a.x ~= b.x then return a.x < b.x end
        return a.y < b.y
    end)
    local slots = {}
    for _, m in ipairs(mons) do slots[m.name] = slotOf(m) end
    return mons, slots
end

local function deskOf(id) return (id - 1) % DESKS + 1 end
local function slotOfId(id) return math.floor((id - 1) / DESKS) end

-- windows shown on another screen while their own screen was gone:
-- address -> workspace to go back to. Kept in a file, because opening or
-- closing the lid reloads this config.
local origins = {}
local function loadOrigins()
    origins = {}
    local f = io.open(ORIGINS_FILE, "r")
    if not f then return end
    for line in f:lines() do
        local addr, id = line:match("^(%S+)%s+(%d+)$")
        if addr then origins[addr] = tonumber(id) end
    end
    f:close()
end
local function saveOrigins()
    local f = io.open(ORIGINS_FILE, "w")
    if not f then return end
    for addr, id in pairs(origins) do f:write(addr, " ", id, "\n") end
    f:close()
end

-- keep all 10 workspaces of every screen alive on that screen, and take back
-- the ones Hyprland parked on another screen while it was gone
local pinned = {}
local function pinDesks()
    local mons, slots = monitorSlots()
    for _, m in ipairs(mons) do
        for n = 1, DESKS do
            local id = slots[m.name] * DESKS + n
            local key = m.name .. ":" .. id
            if not pinned[key] then
                pinned[key] = true
                hl.workspace_rule({ workspace = tostring(id), monitor = m.name, persistent = true })
            end
            local ws = hl.get_workspace(id)
            if ws and ws.monitor and ws.monitor.name ~= m.name then
                hl.dispatch(hl.dsp.workspace.move({ workspace = id, monitor = m.name }))
            end
        end
    end
end

-- windows whose screen is back: return them to their own workspace
local function restoreWindows()
    if next(origins) == nil then return end
    local _, slots = monitorSlots()
    local present = {}
    for _, s in pairs(slots) do present[s] = true end
    local alive = {}
    for _, w in ipairs(hl.get_windows()) do
        alive[w.address] = true
        local id = origins[w.address]
        if id and present[slotOfId(id)] then
            if not (w.workspace and w.workspace.id == id) then
                hl.dispatch(hl.dsp.window.move({ workspace = id, follow = false, window = w }))
            end
            origins[w.address] = nil
        end
    end
    for addr in pairs(origins) do
        if not alive[addr] then origins[addr] = nil end
    end
    saveOrigins()
end

-- a screen is gone (lid closed or unplugged): Hyprland parks its workspaces on
-- another screen, where no desk key reaches them. Show their windows on the same
-- desk number of that screen, and remember where they came from.
local function adoptOrphans()
    local mons, slots = monitorSlots()
    if #mons == 0 then return end -- every screen is off (asleep, locked): wait for them
    local changed = false
    for _, ws in ipairs(hl.get_workspaces()) do
        local slot = ws.monitor and slots[ws.monitor.name]
        if slot and ws.id >= 1 and slotOfId(ws.id) ~= slot then
            local target = slot * DESKS + deskOf(ws.id)
            for _, w in ipairs(hl.get_workspace_windows(ws)) do
                if not origins[w.address] then
                    origins[w.address] = ws.id
                    changed = true
                end
                hl.dispatch(hl.dsp.window.move({ workspace = target, follow = false, window = w }))
            end
        end
    end
    if changed then saveOrigins() end
end

local syncing = false

local function showDesk(n)
    local focused = hl.get_active_monitor()
    if not focused or syncing then return end
    syncing = true
    local cursor = hl.get_cursor_pos()
    local mons, slots = monitorSlots()
    local moved = false
    for _, m in ipairs(mons) do
        local id = slots[m.name] * DESKS + n
        if m.name ~= focused.name and not (m.active_workspace and m.active_workspace.id == id) then
            hl.dispatch(hl.dsp.focus({ monitor = m.name }))
            hl.dispatch(hl.dsp.focus({ workspace = id }))
            moved = true
        end
    end
    if moved then
        hl.dispatch(hl.dsp.focus({ monitor = focused.name }))
        -- focusing a monitor warps the cursor; put it back where it was
        if cursor then hl.dispatch(hl.dsp.cursor.move({ x = cursor.x, y = cursor.y })) end
    end
    local id = slots[focused.name] * DESKS + n
    -- skip if already there, or workspace_back_and_forth would jump away
    if (hl.get_active_workspace() or {}).id ~= id then
        hl.dispatch(hl.dsp.focus({ workspace = id }))
    end
    syncing = false
end

local function currentWorkspace()
    local ws = hl.get_active_workspace()
    if not ws or ws.id < 1 then return 1 end
    return deskOf(ws.id)
end

-- screens come and go in bursts (waking up, lid, docking): act once they settle
local function settle()
    pinDesks()
    restoreWindows()
    adoptOrphans()
    local ws = hl.get_active_workspace()
    if ws and ws.id >= 1 then showDesk(deskOf(ws.id)) end
    -- screens dimmed in software (no DDC/CI) get their dark layer back
    hl.exec_cmd("~/.config/waybar/scripts/dim-screen.py --restore")
end
local settleTimer
local function settleSoon()
    if settleTimer then settleTimer:set_enabled(false) end
    settleTimer = hl.timer(settle, { timeout = 3000, type = "oneshot" })
end

loadOrigins()
settleSoon()
hl.on("hyprland.start", function()
    -- a new session: addresses from an earlier one mean nothing
    origins = {}
    saveOrigins()
    settleSoon()
end)
hl.on("monitor.added", settleSoon)
hl.on("monitor.removed", settleSoon)

-- the bar's desk buttons call these (`hyprctl eval 'desk(3)'`); waybar's own
-- workspace module can't, it only speaks the old hyprctl dispatch syntax
function desk(n) showDesk(n) end
local function refreshBar() hl.exec_cmd("pkill -RTMIN+8 waybar") end
for _, ev in ipairs({ "workspace.active", "window.open", "window.close", "window.move_to_workspace" }) do
    hl.on(ev, refreshBar)
end
-- a popup (launcher, sound, calendar, ...) closes when the desk changes or a window opens
local function closePopups() hl.exec_cmd("~/.config/waybar/scripts/popup.sh --close-all") end
hl.on("workspace.active", closePopups)
hl.on("window.open", closePopups)

-- anything that changes the desk on one monitor (bar click, swipe, ...) moves the others too
hl.on("workspace.active", function()
    if syncing then return end
    local ws = hl.get_active_workspace()
    if not ws or ws.id < 1 then return end
    local n = deskOf(ws.id)
    for _, m in ipairs(hl.get_monitors()) do
        local a = m.active_workspace
        if a and a.id >= 1 and deskOf(a.id) ~= n then
            showDesk(n)
            return
        end
    end
end)

-- previous/next desk (wraps 10 -> 1)
local function stepWorkspace(delta)
    return function() showDesk((currentWorkspace() - 1 + delta) % DESKS + 1) end
end

-- move the active window to desk n on its monitor; with follow, go there too
local function sendToWorkspace(n, follow)
    local m = hl.get_active_monitor()
    if not m then return end
    local _, slots = monitorSlots()
    hl.dispatch(hl.dsp.window.move({ workspace = slots[m.name] * DESKS + n, follow = false }))
    if follow then showDesk(n) end
end

local function sendStep(delta)
    return function() sendToWorkspace((currentWorkspace() - 1 + delta) % DESKS + 1, true) end
end

bind(mainMod .. " + CTRL + left",  stepWorkspace(-1))
bind(mainMod .. " + CTRL + right", stepWorkspace(1))
bind(mainMod .. " + mouse_down",   stepWorkspace(-1))
bind(mainMod .. " + mouse_up",     stepWorkspace(1))

-- desks 1-10
for i = 1, DESKS do
    local key = i % 10
    bind(mainMod .. " + " .. key,            function() showDesk(i) end)
    bind(mainMod .. " + SHIFT + " .. key,    function() sendToWorkspace(i, true) end)
    bind(mainMod .. " + CTRL + " .. key,     function() sendToWorkspace(i, false) end)
end

-- mouse
bind(mainMod .. " + mouse:272", hl.dsp.window.drag(),   { mouse = true })
bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- resize mode: SUPER+R, arrows, Esc
bind(mainMod .. " + R", hl.dsp.submap("resize"))
hl.define_submap("resize", function()
    bind("right",  hl.dsp.window.resize({ x = 15,  y = 0,   relative = true }), { repeating = true })
    bind("left",   hl.dsp.window.resize({ x = -15, y = 0,   relative = true }), { repeating = true })
    bind("up",     hl.dsp.window.resize({ x = 0,   y = -15, relative = true }), { repeating = true })
    bind("down",   hl.dsp.window.resize({ x = 0,   y = 15,  relative = true }), { repeating = true })
    bind("escape", hl.dsp.submap("reset"))
end)

-- media keys
local lr = { locked = true, repeating = true }
-- volume keys show an on-screen bar; click the volume box on the bar for the full popup
bind("XF86AudioRaiseVolume",  exec("~/.config/hypr/scripts/volume.sh up"), lr)
bind("XF86AudioLowerVolume",  exec("~/.config/hypr/scripts/volume.sh down"), lr)
bind("XF86AudioMute",         exec("~/.config/hypr/scripts/volume.sh mute"), { locked = true })
bind("XF86AudioMicMute",      exec("~/.config/hypr/scripts/volume.sh mic-mute"), { locked = true })
bind("XF86MonBrightnessUp",   exec("brightnessctl set +10%"), lr)
bind("XF86MonBrightnessDown", exec("brightnessctl set 10%-"), lr)
bind("XF86AudioPlay",         exec("playerctl play-pause"), { locked = true })
bind("XF86AudioNext",         exec("playerctl next"), { locked = true })
bind("XF86AudioPrev",         exec("playerctl previous"), { locked = true })

-- screenshots
bind("Print",        exec('grim -g "$(slurp)" - | wl-copy'))
bind("CTRL + Print", exec('grim -g "$(slurp)" - | swappy -f -'))

-- SUPER+Up/Down: previous/next workspace (SHIFT = take the window along)
bind(mainMod .. " + up",           stepWorkspace(-1))
bind(mainMod .. " + down",         stepWorkspace(1))
bind(mainMod .. " + SHIFT + up",   sendStep(-1))
bind(mainMod .. " + SHIFT + down", sendStep(1))

-- SUPER+Right/Left: cycle through the windows of this desk on all monitors,
-- left to right across the screens (forward / backward)
local function cycleDeskWindows(step)
    return function()
        local wins = {}
        for _, m in ipairs(hl.get_monitors()) do
            if m.active_workspace then
                for _, w in ipairs(hl.get_workspace_windows(m.active_workspace)) do
                    if w.mapped and not w.hidden then wins[#wins + 1] = w end
                end
            end
        end
        if #wins == 0 then return end
        table.sort(wins, function(a, b)
            if a.at.x ~= b.at.x then return a.at.x < b.at.x end
            return a.at.y < b.at.y
        end)
        local active, current = hl.get_active_window(), 0
        for i, w in ipairs(wins) do
            if active and w.address == active.address then current = i end
        end
        local target = current == 0 and 1 or (current - 1 + step) % #wins + 1
        hl.dispatch(hl.dsp.focus({ window = wins[target] }))
    end
end
bind(mainMod .. " + right", cycleDeskWindows(1))
bind(mainMod .. " + left",  cycleDeskWindows(-1))

-- Zen: ALT+Up/Down = previous/next tab (other apps get normal ALT+Up/Down)
local function zenTab(tabKey, arrow)
    return function()
        local w = hl.get_active_window()
        if w and w.class == "app.zen_browser.zen" then
            hl.dispatch(hl.dsp.send_shortcut({ mods = "CTRL", key = tabKey }))
        else
            hl.dispatch(hl.dsp.send_shortcut({ mods = "ALT", key = arrow }))
        end
    end
end
bind("ALT + down", zenTab("Page_Down", "Down"))
bind("ALT + up",   zenTab("Page_Up",   "Up"))

-- SUPER+N: notification center
bind(mainMod .. " + N", exec("swaync-client -t -sw"))

-- SUPER+L: lock screen
bind(mainMod .. " + L", exec("pidof hyprlock || (hyprctl switchxkblayout all 0; hyprlock)"))

---------------- Power: sleep timer + laptop lid ----------------
hl.on("hyprland.start", function()
    hl.exec_cmd("~/.config/hypr/scripts/idle.sh apply")
    hl.exec_cmd("sleep 1; ~/.config/hypr/scripts/lid.sh check")
end)
-- lid already closed when a screen is plugged in or out: apply it
hl.on("monitor.added",   function() hl.exec_cmd("sleep 1; ~/.config/hypr/scripts/lid.sh check") end)
hl.on("monitor.removed", function() hl.exec_cmd("sleep 1; ~/.config/hypr/scripts/lid.sh check") end)

-- lid closed while an external screen is connected -> switch the laptop panel off
do
    local f = io.open((os.getenv("XDG_RUNTIME_DIR") or "/tmp") .. "/hypr-lid-closed", "r")
    if f then
        local panel = (f:read("*l") or "eDP-1"):gsub("%s+", "")
        f:close()
        hl.monitor({ output = panel, disabled = true })
    end
end
bind("switch:on:Lid Switch",  exec("~/.config/hypr/scripts/lid.sh close"), { locked = true })
bind("switch:off:Lid Switch", exec("~/.config/hypr/scripts/lid.sh open"),  { locked = true })
