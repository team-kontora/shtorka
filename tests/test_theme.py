import pytest

from shtorka import theme


def test_black_matches_the_original_look(qapp):
    sheet = theme.stylesheet("#000000", "flat")
    for shade in ["#111111", "#1a1a1a", "#262626", "#2a2a2a", "#333333", "#3a3a3a", "#444444", "#777777", "#8a8a8a"]:
        assert shade in sheet


def test_text_is_dark_on_light_backgrounds(qapp):
    assert "color: #000000" in theme.stylesheet("#ffffff", "flat")
    assert "color: #ffffff" in theme.stylesheet("#2b5278", "flat")


def test_rounded_adds_corners(qapp):
    assert "radius: 8px" not in theme.stylesheet("#000000", "flat")
    assert "radius: 8px" in theme.stylesheet("#000000", "rounded")


@pytest.mark.parametrize("value", [None, 5, "", "nonsense"])
def test_bad_values_fall_back(qapp, value):
    assert theme.color(value) == theme.DEFAULT_COLOR
    assert theme.style(value) == theme.DEFAULT_STYLE


def test_presets_are_valid(qapp):
    assert all(theme.color(c) == c for c in theme.COLORS.values())


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@pytest.mark.parametrize(("name", "background"), theme.COLORS.items())
def test_presets_keep_text_readable(qapp, name, background):
    sheet = theme.stylesheet(background, "flat")
    text = "#000000" if "color: #000000" in sheet else "#ffffff"
    light, dark = sorted((_luminance(background), _luminance(text)), reverse=True)
    # WCAG AA for normal text
    assert (light + 0.05) / (dark + 0.05) >= 4.5, name
