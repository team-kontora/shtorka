import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32 only")


def _row(pixels):
    return b"".join(bytes((b, g, r, 0)) for r, g, b in pixels)


def test_finds_one_and_two_pixel_lines():
    from shtorka.tgwin import find_divider

    bg, line = (23, 33, 43), (10, 15, 20)
    assert find_divider(_row([bg] * 10 + [line] + [bg] * 10), 0, 20) == 10
    assert find_divider(_row([bg] * 10 + [line] * 2 + [bg] * 10), 0, 20) == 10


def test_ignores_flat_rows_and_wide_shapes():
    from shtorka.tgwin import find_divider

    bg, other = (23, 33, 43), (200, 200, 200)
    assert find_divider(_row([bg] * 30), 0, 28) is None
    assert find_divider(_row([bg] * 10 + [other] * 5 + [bg] * 10), 0, 23) is None
