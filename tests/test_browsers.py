import browsers

ZEN = (
    "/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=launch-script.sh --file-forwarding "
    "app.zen_browser.zen @@u %u @@"
)


def test_family_of_each_installed_kind():
    assert browsers.family("app.zen_browser.zen.desktop", ZEN) == "firefox"
    assert browsers.family("org.mozilla.firefox.desktop", "firefox %u") == "firefox"
    assert browsers.family("google-chrome.desktop", "/usr/bin/google-chrome-stable %U") == "chromium"
    assert browsers.family("brave-browser.desktop", "/usr/bin/brave-browser-stable %U") == "chromium"
    assert browsers.family("org.gnome.Nautilus.desktop", "nautilus --new-window %U") is None
    assert browsers.family("kitty.desktop", "kitty") is None
    assert browsers.family("org.gnome.Zenity.desktop", "zenity") is None
    assert browsers.family("org.kde.knowledge.desktop", "knowledgebase --edge-case") is None
    # a site installed as an app from Chrome is not a browser
    web_app = "/opt/google/chrome/google-chrome --profile-directory=Default --app-id=mncmhfnjabifclfceohglnjfnmaiajlf"
    assert browsers.family("chrome-mncmhfnjabifclfceohglnjfnmaiajlf-Default.desktop", web_app) is None


def test_new_tab_commands_drop_placeholders():
    assert browsers.command(ZEN, "firefox", "tab") == [
        "/usr/bin/flatpak",
        "run",
        "--branch=stable",
        "--arch=x86_64",
        "--command=launch-script.sh",
        "--file-forwarding",
        "app.zen_browser.zen",
        "--new-tab",
        "about:newtab",
    ]
    assert browsers.command("/usr/bin/google-chrome-stable %U", "chromium", "tab") == [
        "/usr/bin/google-chrome-stable",
        "chrome://newtab/",
    ]


def test_private_window_flag_per_browser():
    assert browsers.command("firefox %u", "firefox", "private")[-1] == "--private-window"
    assert browsers.command("/usr/bin/brave-browser-stable %U", "chromium", "private")[-1] == "--incognito"
    assert browsers.command("/usr/bin/microsoft-edge-stable %U", "chromium", "private")[-1] == "--inprivate"


def test_nothing_for_unknown_or_empty():
    assert browsers.command("", "firefox", "tab") is None
    assert browsers.command("kitty", None, "tab") is None
    assert browsers.command('broken "quote', "firefox", "tab") is None
