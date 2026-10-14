import pytest

from shtorka.hotkey import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, parse, spec


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("Ctrl+Space", (MOD_CONTROL, 0x20)),
        ("ctrl + alt + k", (MOD_CONTROL | MOD_ALT, ord("K"))),
        ("Win+Shift+1", (MOD_WIN | MOD_SHIFT, ord("1"))),
        ("Ctrl+`", (MOD_CONTROL, 0xC0)),
        ("Ctrl+Ё", (MOD_CONTROL, 0xC0)),
        ("F9", (0, 0x78)),
        ("Shift+F12", (MOD_SHIFT, 0x7B)),
    ],
)
def test_parse(spec, expected):
    assert parse(spec) == expected


@pytest.mark.parametrize(
    "spec",
    # plain typing must stay plain typing, and nonsense turns the hotkey off rather than guessing
    ["", "Space", "K", "Shift+K", "Ctrl+", "Ctrl+Ctrl+K", "Ctrl+Foo", "Hyper+K", "Ctrl+Ж", None, 42],
)
def test_parse_rejects(spec):
    assert parse(spec) is None


@pytest.mark.parametrize(
    ("modifiers", "vk", "expected"),
    [
        (MOD_CONTROL, 0x20, "Ctrl+Space"),
        (MOD_SHIFT | MOD_CONTROL, ord("Q"), "Ctrl+Shift+Q"),
        (MOD_WIN | MOD_ALT, ord("7"), "Alt+Win+7"),
        (MOD_CONTROL, 0xC0, "Ctrl+`"),
        (0, 0x7B, "F12"),
        (MOD_CONTROL, 0x0D, ""),
        (MOD_CONTROL, 0, ""),
    ],
)
def test_spec(modifiers, vk, expected):
    assert spec(modifiers, vk) == expected


@pytest.mark.parametrize("value", ["Ctrl+Space", "Ctrl+Shift+Q", "Alt+Win+7", "Ctrl+`", "F12"])
def test_spec_reads_back(value):
    assert spec(*parse(value)) == value
