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
