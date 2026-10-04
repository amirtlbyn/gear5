"""
Runs hyprland.lua under luajit with a stub `hl` and returns the binds it makes,
the way a Hyprland reload would see them.

    import lua_binds
    binds = lua_binds.run(user_settings="return { shortcuts = {} }")
    binds[0]  # {"keys": ..., "action": ..., "opts": ..., "description": ..., "submap": ...}
"""

import json
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HYPRLAND_LUA = os.path.join(ROOT, "config", "hypr", "hyprland.lua")
LUAJIT = shutil.which("luajit")

# every hl.x.y(...) is a stub that returns its own call as text, so an action
# like hl.dsp.window.close() is the string "hl.dsp.window.close()"
HARNESS = r"""
local function show(v)
    if type(v) == "table" then
        local names, byName = {}, {}
        for k, x in pairs(v) do names[#names + 1] = tostring(k); byName[tostring(k)] = x end
        table.sort(names)
        local parts = {}
        for _, k in ipairs(names) do parts[#parts + 1] = k .. "=" .. show(byName[k]) end
        return "{" .. table.concat(parts, ",") .. "}"
    elseif type(v) == "function" then
        return "<function>"
    end
    return tostring(v)
end
local function clean(s) return (tostring(s):gsub("[\t\n]", " ")) end

local out, submap = {}, ""
local function proxy(path)
    return setmetatable({}, {
        __index = function(_, k) return proxy(path .. "." .. k) end,
        __call = function(_, ...)
            local args = {}
            for i = 1, select("#", ...) do args[i] = show((select(i, ...))) end
            return path .. "(" .. table.concat(args, ", ") .. ")"
        end,
    })
end

hl = proxy("hl")
hl.bind = function(keys, action, opts)
    -- like Hyprland 0.56: keys it can't read are logged, not bound, and give nil
    if REJECT[keys] then return nil end
    local o, description = {}, ""
    for k, v in pairs(opts or {}) do
        if k == "description" then description = v else o[k] = v end
    end
    out[#out + 1] = table.concat({ clean(keys), clean(show(action)), clean(show(o)), clean(description), submap }, "\t")
    return {}
end
hl.define_submap = function(name, fn)
    submap = name
    fn()
    submap = ""
end

if USER_SETTINGS then
    package.preload["user-settings"] = assert(loadstring(USER_SETTINGS, "=user-settings"))
end
dofile(LUA_FILE)
io.write(table.concat(out, "\n"), "\n")
"""


def run(user_settings=None, reject=(), lua_file=HYPRLAND_LUA):
    """The binds `lua_file` makes, in order, as dicts. `user_settings` is the text of
    the user-settings module (None: no such file); `reject` lists key texts the stub
    hl.bind refuses, as Hyprland does for keys it cannot read."""
    prelude = (
        f"LUA_FILE = {json.dumps(lua_file)}\n"
        f"USER_SETTINGS = {json.dumps(user_settings) if user_settings is not None else 'nil'}\n"
        "REJECT = {" + ", ".join(f"[{json.dumps(k)}] = true" for k in reject) + "}\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "harness.lua")
        with open(script, "w") as f:
            f.write(prelude + HARNESS)
        done = subprocess.run([LUAJIT, script], cwd=tmp, capture_output=True, text=True, check=True)
    binds = []
    for line in done.stdout.splitlines():
        keys, action, opts, description, submap = line.split("\t")
        binds.append(dict(keys=keys, action=action, opts=opts, description=description, submap=submap))
    return binds


def by_keys(binds):
    """The binds as {keys: bind}, to look one up by its keys."""
    return {b["keys"]: b for b in binds}
