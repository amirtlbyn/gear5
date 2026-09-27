"""
The bar popups as pages of the Settings app.

Each popup keeps its widgets and actions in a panel class (DisplaysPanel, PowerPanel,
...) that both its own popup window and Settings use. A panel talks to whatever shows
it through a host:

    host.close()          the popup closes; Settings does nothing
    host.is_shown()       True while the panel can be seen (refresh timers check it)
    host.embedded         True in Settings: hide what opens another app

A panel has on_show() and on_hide() (it came into view / went away), and may have
on_key(keyval) and on_escape() (True when Esc was used, e.g. to close an open row),
and stop() (end its helper processes when Settings quits).

    import panel
    mod = panel.load("wifi-menu")          # the popup's module, without its window
    css = panel.scoped_css(mod.STYLE, colors, "panel-wifi")
"""

import importlib.util
import os
import re
import sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))

# the panel sits on a Settings page, not in a floating popup box
OVERRIDES = """
.{root} .popup {{ background: transparent; border: none; box-shadow: none; margin: 0; padding: 0;
                  border-radius: 0; }}
.{root} .title {{ font-size: 22px; font-weight: 800; }}
"""


def load(name):
    """The popup module (e.g. "wifi-menu" -> wifi-menu.py), imported once."""
    mod_name = name.replace("-", "_")
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, os.path.join(SCRIPTS, name + ".py"))
    if spec is None or spec.loader is None:
        raise ImportError(f"no popup named {name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        del sys.modules[mod_name]
        raise
    return mod


def scoped_css(style, colors, root):
    """A popup's CSS for use inside Settings: every rule only applies under .root,
    the theme colors are written in (so two panels' @define-color never clash), and
    the rules for the popup's own window and backdrop are left out."""

    def color(m):
        return colors.get(m.group(1), m.group(0))

    body = re.sub(r"@define-color[^;]*;", "", style)
    body = re.sub(r"@([A-Za-z_]\w*)", color, body)
    return scope(body, root) + OVERRIDES.format(root=root)


def scope(style, root):
    """Every rule of style only for widgets inside .root; window and backdrop rules dropped."""
    body = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
    rules = []
    for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", body):
        kept = [
            f".{root} {s}"
            for s in (s.strip() for s in selectors.split(","))
            if s and not s.startswith(("window", ".backdrop"))
        ]
        if kept:
            rules.append(", ".join(kept) + " {" + declarations + "}")
    return "\n".join(rules) + "\n"
