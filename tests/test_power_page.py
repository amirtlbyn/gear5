"""Settings shows the battery on the Battery page only, and brightness on the
Displays page only: the page map gives no other page a battery or brightness
panel (the quick settings popup keeps its own cards)."""

import panel

settings = panel.load("settings")


def test_no_settings_page_but_battery_shows_a_battery_panel():
    """BATT-1: given the Settings page map, when a page other than Battery is
    built, then it gets no battery panel. No page maps a panel with Battery in
    its name, and the Battery page keeps its limits panel."""
    for key, panels in settings.PANELS.items():
        names = [cls for _mod, cls in panels]
        if key == "battery":
            assert "BatteryLimitsPanel" in names, names
        else:
            assert not [c for c in names if "Battery" in c], (key, names)


def test_power_page_maps_no_brightness():
    """BRT-3: given the Settings page map, when the Power & sleep page is built,
    then it is the power panel alone, and no page maps a brightness panel (the
    quick settings card keeps its own, outside Settings)."""
    assert settings.PANELS["power"] == [("power-popup", "PowerPanel")]
    for key, panels in settings.PANELS.items():
        assert not [c for _m, c in panels if "Brightness" in c], (key, panels)
