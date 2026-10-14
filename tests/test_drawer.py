import pytest
from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from shtorka import drawer, hotkey, tgwin
from shtorka.store import Template

TELEGRAM = tgwin.Window(hwnd=1001, left=0, top=0, right=1200, bottom=800)


class FakeStore(QObject):
    changed = Signal()

    def __init__(self, templates):
        super().__init__()
        self.templates = templates

    def load(self):
        return list(self.templates)


@pytest.fixture
def focus(monkeypatch):
    """Windows the drawer handed the focus to; nothing is really activated or typed."""
    activated = []
    monkeypatch.setattr(tgwin, "activate", activated.append)
    monkeypatch.setattr(tgwin, "send_ctrl_v", lambda: None)
    return activated


@pytest.fixture
def make(qapp, focus):
    made = []

    def make(hotkey="Ctrl+Space"):
        templates = [
            Template("Приветствие", "Здравствуйте!"),
            Template("Сроки доставки", "2–3 дня"),
            Template("Реквизиты", "ИНН ..."),
        ]
        cfg = {"process_names": [], "color": "#000000", "style": "flat", "auto_update": False, "hotkey": hotkey}
        d = drawer.Drawer(cfg, FakeStore(templates))
        # the drawer must not go looking for a real Telegram
        d._tick.stop()
        d._tg = TELEGRAM
        d.resize(800, drawer.TAB_HEIGHT)
        d.show()
        made.append(d)
        return d

    yield make
    for d in made:
        d.close()
        d.deleteLater()


def type_into(field, text):
    # QTest.keyClicks sends only Latin-1, so Cyrillic goes as key events that carry their text, as Windows sends them
    for char in text:
        QApplication.sendEvent(field, QKeyEvent(QEvent.KeyPress, 0, Qt.NoModifier, char))


def shown(d):
    return [row.tpl.title for row in d._rows]


def test_hover_mode_has_no_search(make):
    d = make()
    assert d.search.isHidden()
    assert shown(d) == ["Приветствие", "Сроки доставки", "Реквизиты"]


def test_typing_filters_the_list(make):
    d = make()
    d.toggle_keyboard()
    assert d.search.isVisibleTo(d)
    type_into(d.search, "дост")
    assert shown(d) == ["Сроки доставки"]
    # the search line, one row and the add button
    assert d._target() == drawer.TAB_HEIGHT + 3 * drawer.ROW_HEIGHT


def test_arrows_and_enter_paste_the_chosen_template(make, focus):
    d = make()
    pasted = []
    d.paste = pasted.append
    d.toggle_keyboard()
    QTest.keyClick(d.search, Qt.Key_Down)
    QTest.keyClick(d.search, Qt.Key_Down)
    QTest.keyClick(d.search, Qt.Key_Down)
    QTest.keyClick(d.search, Qt.Key_Up)
    assert [row.property("selected") for row in d._rows] == [False, True, False]
    QTest.keyClick(d.search, Qt.Key_Return)
    assert [t.title for t in pasted] == ["Сроки доставки"]


def selected(d):
    return [row.tpl.title for row in d._rows if row.property("selected")]


def test_tab_and_shift_tab_cycle_through_the_list(make):
    d = make()
    d.toggle_keyboard()
    QTest.keyClick(d.search, Qt.Key_Tab)
    assert selected(d) == ["Сроки доставки"]
    QTest.keyClick(d.search, Qt.Key_Tab)
    QTest.keyClick(d.search, Qt.Key_Tab)
    # past the last one Tab comes back to the first, and Shift+Tab goes from the first to the last
    assert selected(d) == ["Приветствие"]
    QTest.keyClick(d.search, Qt.Key_Backtab, Qt.ShiftModifier)
    assert selected(d) == ["Реквизиты"]


def test_paste_leaves_the_keyboard_mode_for_telegram(make, focus):
    d = make()
    d.toggle_keyboard()
    type_into(d.search, "рекв")
    QTest.keyClick(d.search, Qt.Key_Return)
    assert not d._keyboard and d.search.isHidden()
    assert focus[-1] == TELEGRAM.hwnd
    # the full list is back for the next hover
    assert len(shown(d)) == 3


def test_escape_gives_the_focus_back(make, focus):
    d = make()
    d.toggle_keyboard()
    type_into(d.search, "прив")
    QTest.keyClick(d.search, Qt.Key_Escape)
    assert not d._keyboard and not d._open
    assert focus[-1] == TELEGRAM.hwnd
    assert d.search.text() == ""


def test_hotkey_again_closes(make):
    d = make()
    d.toggle_keyboard()
    d.toggle_keyboard()
    assert not d._keyboard


def test_nothing_found_leaves_the_add_button(make):
    d = make()
    d.toggle_keyboard()
    type_into(d.search, "ничего такого")
    assert shown(d) == [] and d.scroll.isHidden()
    QTest.keyClick(d.search, Qt.Key_Return)
    assert d._keyboard


def test_no_hotkey_no_tooltip(make):
    d = make(hotkey="")
    assert d.hotkey.keys is None
    assert d.tab.toolTip() == ""


def press(widget, key, modifiers=Qt.NoModifier, vk=0, text=""):
    # what Windows sends: the Qt key plus the layout-independent virtual key
    QApplication.sendEvent(widget, QKeyEvent(QEvent.KeyPress, key, modifiers, 0, vk, 0, text))


@pytest.fixture
def free(monkeypatch):
    """Which combinations other programs hold; nothing is registered for real."""
    taken = set()
    monkeypatch.setattr(hotkey, "available", lambda keys: keys not in taken)
    return taken


def test_capture_reads_the_physical_key(qapp, free):
    dialog = drawer.HotkeyDialog(None, "Ctrl+Space")
    # Ctrl+Й on a Russian layout is the Q key
    press(dialog.capture, Qt.Key_Q, Qt.ControlModifier | Qt.ShiftModifier, vk=ord("Q"), text="Й")
    assert dialog.value == "Ctrl+Shift+Q"
    assert dialog.capture.text() == "Ctrl+Shift+Q"
    assert dialog.save.isEnabled()


def test_capture_shows_modifiers_while_they_are_held(qapp, free):
    dialog = drawer.HotkeyDialog(None, "Ctrl+Space")
    press(dialog.capture, Qt.Key_Alt, Qt.AltModifier)
    assert dialog.capture.text() == "Alt+…"
    QApplication.sendEvent(dialog.capture, QKeyEvent(QEvent.KeyRelease, Qt.Key_Alt, Qt.NoModifier))
    assert dialog.capture.text() == "Ctrl+Space"
    assert dialog.value == "Ctrl+Space"


@pytest.mark.parametrize(
    ("key", "modifiers", "vk", "hint"),
    [
        (Qt.Key_K, Qt.ShiftModifier, ord("K"), "Добавьте Ctrl, Alt или Win"),
        (Qt.Key_Home, Qt.ControlModifier, 0x24, "Подойдут буквы"),
    ],
)
def test_unusable_combinations_cannot_be_saved(qapp, free, key, modifiers, vk, hint):
    dialog = drawer.HotkeyDialog(None, "Ctrl+Space")
    press(dialog.capture, key, modifiers, vk=vk)
    assert hint in dialog.hint.text()
    assert not dialog.save.isEnabled()


def test_taken_combination_cannot_be_saved(qapp, free):
    free.add(hotkey.parse("Alt+Q"))
    dialog = drawer.HotkeyDialog(None, "Ctrl+Space")
    press(dialog.capture, Qt.Key_Q, Qt.AltModifier, vk=ord("Q"))
    assert "занято" in dialog.hint.text()
    assert not dialog.save.isEnabled()


def test_turn_off(qapp, free):
    dialog = drawer.HotkeyDialog(None, "Ctrl+Space")
    dialog._turn_off()
    assert dialog.result() == drawer.QDialog.Accepted and dialog.value == ""


def test_set_hotkey_switches_at_once(make):
    d = make()
    d.set_hotkey("Alt+Q")
    assert d.hotkey.keys == hotkey.parse("Alt+Q")
    assert d.cfg["hotkey"] == "Alt+Q"
    assert d.tab.toolTip().startswith("Alt+Q")
    d.set_hotkey("")
    assert d.hotkey.keys is None and d.tab.toolTip() == ""
