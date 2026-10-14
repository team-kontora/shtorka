"""The drawer window: a tab over Telegram's title bar that drops a list of template names on hover."""
from ctypes import wintypes

from PySide6.QtCore import QEasingCurve, QEvent, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QCursor, QFont, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import hotkey, tgwin, theme
from .store import BrokenFile, Store, Template, search

# the tab covers Telegram's title bar from the line that ends the chat list up to the window buttons;
# this offset is the fallback for when that line cannot be found on screen
TAB_LEFT_GAP = 72
# ticks between looks at the screen for that line
DIVIDER_TICKS = 5
TAB_HEIGHT = 24
# minimize / maximize / close must always stay reachable
CAPTION_BUTTONS = 108
LIST_WIDTH = 316
ROW_HEIGHT = 32
MAX_ROWS = 10
# ticks the cursor may spend outside before the list closes
LEAVE_TICKS = 3
# how long a click waits for a possible second one before it pastes
CLICK_DELAY_MS = 250
# ticks Telegram has to stay put after a move before the drawer comes back
SETTLE_TICKS = 2
TAB_TEXT = "Шаблоны"
# how long the drawer waits for the focus after the hotkey before it gives the keyboard mode up
FOCUS_CHECK_MS = 300


def _elided(text: str, width: int) -> str:
    font = QFont("Segoe UI")
    font.setPixelSize(13)
    return QFontMetrics(font).elidedText(text, Qt.ElideRight, width)


class Row(QLabel):
    copy = Signal(Template)
    paste = Signal(Template)
    menu = Signal(Template)

    def __init__(self, tpl: Template):
        super().__init__(_elided(tpl.title, LIST_WIDTH - 36))
        self.tpl = tpl
        self._skip_release = False
        self.setObjectName("row")
        self.setTextFormat(Qt.PlainText)
        self.setAttribute(Qt.WA_Hover)
        self.setFixedHeight(ROW_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tpl.text)
        # a click pastes only once it is clear that no second click follows
        self._click = QTimer(self, singleShot=True, interval=CLICK_DELAY_MS)
        self._click.timeout.connect(lambda: self.paste.emit(self.tpl))

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self.rect().contains(event.position().toPoint()):
            return
        # the release that ends a double click must not paste
        if self._skip_release:
            self._skip_release = False
            return
        self._click.start()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._click.stop()
            self._skip_release = True
            self.copy.emit(self.tpl)

    def contextMenuEvent(self, event):
        self.menu.emit(self.tpl)


class SearchField(QLineEdit):
    """The query line of the keyboard mode; it hands the keys that move through the list to the drawer."""

    # how far to move, and whether to wrap around the ends of the list
    step = Signal(int, bool)
    submit = Signal()
    cancel = Signal()

    def event(self, event):
        # Qt takes Tab for moving the focus before keyPressEvent sees it; here it cycles through the list
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.step.emit(-1 if event.key() == Qt.Key_Backtab else 1, True)
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Down, Qt.Key_Up):
            self.step.emit(1 if key == Qt.Key_Down else -1, False)
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self.submit.emit()
        elif key == Qt.Key_Escape:
            self.cancel.emit()
        else:
            super().keyPressEvent(event)


class Tab(QLabel):
    """The strip over Telegram's title bar; it passes window dragging through."""

    drag = Signal()
    maximize = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.maximize.emit()


class TemplateDialog(QDialog):
    def __init__(self, parent, tpl: Template | None = None):
        super().__init__(parent)
        self.setWindowTitle("Изменить шаблон" if tpl else "Новый шаблон")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.resize(420, 320)

        self.title = QLineEdit(tpl.title if tpl else "")
        self.title.setPlaceholderText("Название")
        self.text = QPlainTextEdit(tpl.text if tpl else "")
        self.text.setPlaceholderText("Текст сообщения")

        buttons = QDialogButtonBox()
        buttons.addButton("Сохранить", QDialogButtonBox.AcceptRole)
        buttons.addButton("Отмена", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.text, 1)
        layout.addWidget(buttons)

    def accept(self):
        if self.text.toPlainText().strip():
            super().accept()
        else:
            self.text.setFocus()

    def values(self) -> tuple[str, str]:
        text = self.text.toPlainText().strip()
        title = self.title.text().strip() or text.splitlines()[0][:40]
        return title, text


class KeyCapture(QLineEdit):
    """Shows the combination pressed in it instead of taking typing."""

    changed = Signal()

    def __init__(self, value: str):
        super().__init__(value)
        self.value = value
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignCenter)
        self.setPlaceholderText("Нажмите сочетание")

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # it is a display, not text to edit
        self.deselect()

    def keyPressEvent(self, event):
        modifiers = 0
        for qt, flag in (
            (Qt.ControlModifier, hotkey.MOD_CONTROL),
            (Qt.AltModifier, hotkey.MOD_ALT),
            (Qt.ShiftModifier, hotkey.MOD_SHIFT),
            (Qt.MetaModifier, hotkey.MOD_WIN),
        ):
            if event.modifiers() & qt:
                modifiers |= flag
        key = event.key()
        if not modifiers and key in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            # the dialog's own keys: cancel and save
            event.ignore()
            return
        held = {
            Qt.Key_Control: hotkey.MOD_CONTROL,
            Qt.Key_Alt: hotkey.MOD_ALT,
            Qt.Key_Shift: hotkey.MOD_SHIFT,
            Qt.Key_Meta: hotkey.MOD_WIN,
        }
        if key in held:
            # the combination is still being pressed; Qt may leave the key just pressed out of modifiers()
            self.setText("+".join(hotkey.modifier_names(modifiers | held[key])) + "+…")
            return
        self.value = hotkey.spec(modifiers, event.nativeVirtualKey())
        self.setText(self.value or "+".join([*hotkey.modifier_names(modifiers), event.text().upper() or "?"]))
        self.changed.emit()

    def keyReleaseEvent(self, event):
        # modifiers let go without a key: show the last whole combination again
        if self.text().endswith("…"):
            self.setText(self.value)


class HotkeyDialog(QDialog):
    def __init__(self, parent, value: str):
        super().__init__(parent)
        self.setWindowTitle("Горячая клавиша")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.resize(360, 0)

        self.capture = KeyCapture(value)
        self.capture.changed.connect(self._check)
        self.hint = QLabel()
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        # room for two lines, so that a longer hint does not get cut off
        self.hint.setMinimumHeight(2 * self.hint.fontMetrics().lineSpacing() + 4)

        buttons = QDialogButtonBox()
        self.save = buttons.addButton("Сохранить", QDialogButtonBox.AcceptRole)
        off = buttons.addButton("Отключить", QDialogButtonBox.ResetRole)
        buttons.addButton("Отмена", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        off.clicked.connect(self._turn_off)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Нажмите сочетание, которое будет открывать шторку в Telegram:"))
        layout.addWidget(self.capture)
        layout.addWidget(self.hint)
        layout.addWidget(buttons)
        self.capture.setFocus()
        self._check()

    @property
    def value(self) -> str:
        return self.capture.value

    def _check(self):
        problem = self.problem(self.value)
        self.hint.setText(problem or "Сочетание работает, пока активен Telegram, и не мешает другим программам.")
        self.save.setEnabled(not problem)

    @staticmethod
    def problem(value: str) -> str:
        if not value:
            return "Подойдут буквы, цифры, пробел, ` и F1–F24 вместе с Ctrl, Alt или Win."
        keys = hotkey.parse(value)
        if not keys:
            return "Добавьте Ctrl, Alt или Win, иначе сочетание будет мешать набору текста."
        if not hotkey.available(keys):
            return "Это сочетание уже занято другой программой."
        return ""

    def _turn_off(self):
        self.capture.value = ""
        super().accept()


class Drawer(QWidget):
    def __init__(self, cfg: dict, store: Store):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.cfg = cfg
        self.store = store
        self._tg: tgwin.Window | None = None
        self._open = False
        # a menu or dialog of ours is up: leave the drawer exactly as it is
        self._busy = False
        # after a paste the cursor has to leave before hovering opens the list again
        self._armed = True
        self._misses = 0
        self._count = 0
        self._templates: list[Template] = []
        self._rows: list[Row] = []
        self._selected = 0
        # opened with the hotkey: typing filters the list, and the list stays open wherever the cursor is
        self._keyboard = False
        self.hotkey = hotkey.Hotkey(cfg.get("hotkey"))
        self._tg_rect = None
        self._moving = False
        self._still = 0
        # where the chat list ends, in pixels from Telegram's left edge, and the window width it was seen at
        self._divider: int | None = None
        self._divider_width = 0
        self._ticks = 0
        # animated height
        self._extent = float(TAB_HEIGHT)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        # the list is narrower than the tab; the rest of the window stays see-through
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.tab = Tab(TAB_TEXT)
        self.tab.drag.connect(lambda: self._tg and tgwin.drag(self._tg.hwnd))
        self.tab.maximize.connect(lambda: self._tg and tgwin.toggle_maximize(self._tg.hwnd))
        self.tab.setObjectName("tab")
        self.tab.setAlignment(Qt.AlignCenter)
        self.tab.setFixedHeight(TAB_HEIGHT)
        self.tab.setProperty("open", False)
        self._show_hotkey()

        self.search = SearchField()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Поиск")
        self.search.setFixedHeight(ROW_HEIGHT)
        self.search.hide()
        self.search.textChanged.connect(self._fill)
        self.search.step.connect(self._step)
        self.search.submit.connect(self._paste_selected)
        self.search.cancel.connect(self.close_keyboard)

        self.rows = QVBoxLayout()
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        holder = QWidget()
        holder.setLayout(self.rows)
        self.scroll = scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(holder)

        add = QPushButton("+ Добавить шаблон")
        add.setObjectName("add")
        add.setFixedHeight(ROW_HEIGHT)
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(lambda: self.edit(None))

        # Ignored lets the list shrink to nothing while the drawer is closed
        self.panel = QWidget()
        self.panel.setObjectName("panel")
        self.panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.panel.setFixedWidth(LIST_WIDTH)
        body = QVBoxLayout(self.panel)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.search)
        body.addWidget(scroll, 1)
        body.addWidget(add)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.tab)
        # the pad shifts the list so that it drops under the cursor
        self.pad = QWidget()
        self.pad.setFixedWidth(0)
        below = QHBoxLayout()
        below.setSpacing(0)
        below.addWidget(self.pad)
        below.addWidget(self.panel)
        below.addStretch(1)
        root.addLayout(below, 1)

        self._toast = QTimer(self, singleShot=True, interval=1500)
        self._toast.timeout.connect(lambda: self.tab.setText(TAB_TEXT))

        self._anim = QVariantAnimation(self, duration=140, easingCurve=QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_extent)

        self.apply_look()
        store.changed.connect(self.refresh)
        self.refresh()

        self._tick = QTimer(self, interval=100)
        self._tick.timeout.connect(self.follow)
        self._tick.start()

    # --- docking -------------------------------------------------------------

    def follow(self):
        if self._busy:
            return
        names = self.cfg["process_names"]
        self._tg = tgwin.find_main_window(names)
        if not self._tg or not (self._has_focus() or tgwin.foreground_is(names)):
            self._tg_rect = None
            self._moving = False
            self._hide()
            return
        if self._is_moving():
            self._hide()
            return
        self._track_hover()
        self._ticks += 1
        if not self._open and (self._divider is None or self._ticks % DIVIDER_TICKS == 0):
            self._find_divider()
        self._place()
        if not self.isVisible():
            self.show()
            # showing resets the size Qt did not set itself, so apply it again
            self._place()
        self.hotkey.hold(int(self.winId()), True)

    def _hide(self):
        # other programs get the keys back while Telegram is in the background
        self.hotkey.hold(int(self.winId()), False)
        self._leave_keyboard()
        self.hide()
        self._set_open(False, animate=False)

    def _is_moving(self) -> bool:
        """True while Telegram is being moved or resized; the drawer stays away until it settles."""
        tg = self._tg
        rect = (tg.left, tg.top, tg.right, tg.bottom)
        changed = self._tg_rect not in (None, rect)
        self._tg_rect = rect
        if changed:
            self._moving = True
        if self._moving:
            # a paused drag still counts: wait for the mouse button to come up
            if changed or tgwin.mouse_down():
                self._still = 0
            else:
                self._still += 1
                self._moving = self._still < SETTLE_TICKS
        return self._moving

    def _has_focus(self) -> bool:
        # the drawer or one of its dialogs; the tray menu must not bring the drawer up
        window = QApplication.activeWindow()
        return window is self or isinstance(window, QDialog)

    def _track_hover(self):
        if self._keyboard:
            return
        inside = False
        pos = self.mapFromGlobal(QCursor.pos())
        if self.isVisible():
            inside = self.tab.geometry().contains(pos) or (self._open and self.panel.geometry().contains(pos))
        if inside:
            self._misses = 0
            if self._armed and not self._open:
                width = min(LIST_WIDTH, self.width())
                self.panel.setFixedWidth(width)
                self.pad.setFixedWidth(max(0, min(pos.x() - width // 2, self.width() - width)))
                self._set_open(True)
        else:
            self._armed = True
            self._misses += 1
            if self._open and self._misses >= LEAVE_TICKS:
                self._set_open(False)

    def _target(self) -> float:
        if not self._open:
            return float(TAB_HEIGHT)
        # the add button, and the search line in keyboard mode
        extra = 2 if self._keyboard else 1
        return float(TAB_HEIGHT + (min(self._count, MAX_ROWS) + extra) * ROW_HEIGHT)

    def _set_open(self, is_open: bool, animate: bool = True):
        self._open = is_open
        if self.tab.property("open") != is_open:
            # the rounded style squares the tab's corners while the list hangs from it
            self.tab.setProperty("open", is_open)
            self.tab.style().unpolish(self.tab)
            self.tab.style().polish(self.tab)
        target = self._target()
        self._anim.stop()
        if target == self._extent:
            return
        if animate:
            self._anim.setStartValue(self._extent)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._extent = target

    def _place(self):
        tg = self._tg
        if not tg:
            return
        scale = tgwin.scale(tg.hwnd)
        work = tgwin.work_area(tg.hwnd)
        # a windowed Telegram has a one-pixel frame line above its title bar
        frame = 0 if tgwin.is_maximized(tg.hwnd) else 1
        left, top = max(tg.left, work.left), max(tg.top, work.top) + frame
        x = left + (self._divider if self._divider is not None else frame + round(TAB_LEFT_GAP * scale))
        width = max(0, min(tg.right, work.right) - frame - round(CAPTION_BUTTONS * scale) - x)
        height = min(round(self._extent * scale), tg.bottom - top)
        geometry = (x, top, width, height)
        # compared with where the window really is, not where it was put last: Windows moves it by itself
        # when it lands on a monitor with another scale, after a display change or on waking up
        hwnd = int(self.winId())
        if tgwin.geometry(hwnd) != geometry:
            tgwin.move(hwnd, *geometry)

    def _find_divider(self):
        tg = self._tg
        scale = tgwin.scale(tg.hwnd)
        work = tgwin.work_area(tg.hwnd)
        frame = 0 if tgwin.is_maximized(tg.hwnd) else 1
        left, top = max(tg.left, work.left), max(tg.top, work.top) + frame
        width = min(tg.right, work.right) - left
        # a row just under the title bar crosses the chat list, its end line and the chat header
        row = tgwin.screen_row(left, top + round((TAB_HEIGHT + 3) * scale), width)
        found = tgwin.find_divider(row, round(100 * scale), width - round((CAPTION_BUTTONS + 150) * scale))
        if found is not None:
            self._divider, self._divider_width = found, width
        elif width != self._divider_width:
            # the layout changed and the line is gone (a narrow, single-column window)
            self._divider = None

    def _set_extent(self, value):
        self._extent = float(value)
        self._place()

    # --- keyboard -------------------------------------------------------------

    def nativeEvent(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            if wintypes.MSG.from_address(int(message)).message == hotkey.WM_HOTKEY:
                # a menu or dialog of ours keeps the keyboard
                if not self._busy:
                    self.toggle_keyboard()
                return True, 0
        return super().nativeEvent(event_type, message)

    def _show_hotkey(self):
        self.tab.setToolTip(f"{self.cfg['hotkey']} — открыть с клавиатуры" if self.hotkey.keys else "")

    def set_hotkey(self, value: str):
        """Switch to another combination; the next tick registers it."""
        self.hotkey.hold(int(self.winId()), False)
        self.cfg["hotkey"] = value
        self.hotkey = hotkey.Hotkey(value)
        self._show_hotkey()

    def choose_hotkey(self) -> str | None:
        """Ask for a new combination; returns it ("" for none), or None if the user cancelled."""
        # let the current one go, so that it can be pressed in the dialog and is not taken for "busy"
        self.hotkey.hold(int(self.winId()), False)
        dialog = HotkeyDialog(self, self.cfg.get("hotkey") or "")
        self._busy = True
        try:
            accepted = dialog.exec() == QDialog.Accepted
        finally:
            self._busy = False
        if not accepted:
            return None
        self.set_hotkey(dialog.value)
        return dialog.value

    def toggle_keyboard(self):
        if self._keyboard:
            self.close_keyboard()
        elif self.isVisible():
            self._open_keyboard()

    def _open_keyboard(self):
        self._keyboard = True
        width = min(LIST_WIDTH, self.width())
        self.panel.setFixedWidth(width)
        # under the middle of the tab: with the keyboard nothing points anywhere else
        self.pad.setFixedWidth(max(0, (self.width() - width) // 2))
        self.search.show()
        self._fill()
        self._set_open(True)
        # the hotkey gives this process the right to take the focus from Telegram
        tgwin.activate(int(self.winId()))
        self.activateWindow()
        self.search.setFocus()
        QTimer.singleShot(FOCUS_CHECK_MS, self._check_focus)

    def _check_focus(self):
        # without the focus the typing would go to Telegram while the list waited for it
        if self._keyboard and not self.isActiveWindow():
            self._leave_keyboard()
            self._set_open(False)

    def close_keyboard(self):
        """Fold the list and give the focus back to Telegram."""
        self._leave_keyboard()
        self._set_open(False)
        if self._tg:
            tgwin.activate(self._tg.hwnd)

    def _leave_keyboard(self):
        if not self._keyboard:
            return
        self._keyboard = False
        self.search.hide()
        self.search.clear()
        self._fill()

    def changeEvent(self, event):
        super().changeEvent(event)
        # a click into Telegram or any other window ends the keyboard mode; our own menus and dialogs do not
        if event.type() == QEvent.ActivationChange and self._keyboard and not self._busy and not self.isActiveWindow():
            self._leave_keyboard()
            self._set_open(False)

    def _step(self, delta: int, wrap: bool):
        index = self._selected + delta
        if wrap and self._rows:
            index %= len(self._rows)
        self._select(index)

    def _select(self, index: int):
        if not self._rows:
            self._selected = 0
            return
        self._selected = max(0, min(index, len(self._rows) - 1))
        for i, row in enumerate(self._rows):
            selected = self._keyboard and i == self._selected
            if row.property("selected") != selected:
                row.setProperty("selected", selected)
                row.style().unpolish(row)
                row.style().polish(row)
        self.scroll.ensureWidgetVisible(self._rows[self._selected], 0, 0)

    def _paste_selected(self):
        if self._rows:
            self.paste(self._rows[self._selected].tpl)

    def apply_look(self):
        self.setStyleSheet(theme.stylesheet(self.cfg.get("color"), self.cfg.get("style")))

    # --- templates -----------------------------------------------------------

    def refresh(self):
        self._templates = self.store.load()
        self._fill()

    def _fill(self):
        """Rows for the templates that match the query; for all of them outside the keyboard mode."""
        while item := self.rows.takeAt(0):
            if widget := item.widget():
                widget.deleteLater()
        shown = search(self._templates, self.search.text() if self._keyboard else "")
        self._rows = []
        for tpl in shown:
            row = Row(tpl)
            row.copy.connect(self.copy)
            row.paste.connect(self.paste)
            row.menu.connect(self.show_menu)
            self.rows.addWidget(row)
            self._rows.append(row)
        self.rows.addStretch(1)
        self._count = len(shown)
        # an empty list would still take room from the add button, which is all the drawer opens to then
        self.scroll.setVisible(bool(shown))
        self._select(0)
        # the list height follows the number of rows
        self._set_open(self._open)

    def copy(self, tpl: Template):
        QGuiApplication.clipboard().setText(tpl.text)
        self._flash("Скопировано ✓")

    def paste(self, tpl: Template):
        QGuiApplication.clipboard().setText(tpl.text)
        if not self._tg:
            return
        self._leave_keyboard()
        tgwin.activate(self._tg.hwnd)
        # give Telegram a moment to take focus before the keystroke
        QTimer.singleShot(150, tgwin.send_ctrl_v)
        self._armed = False
        self._set_open(False)

    def show_menu(self, tpl: Template):
        menu = QMenu(self)
        menu.addAction("Вставить в чат", lambda: self.paste(tpl))
        menu.addAction("Скопировать", lambda: self.copy(tpl))
        menu.addSeparator()
        menu.addAction("Изменить", lambda: self.edit(tpl))
        menu.addAction("Удалить", lambda: self.remove(tpl))
        self._busy = True
        try:
            menu.exec(QCursor.pos())
        finally:
            self._busy = False

    def edit(self, tpl: Template | None):
        dialog = TemplateDialog(self, tpl)
        self._busy = True
        try:
            accepted = dialog.exec() == QDialog.Accepted
        finally:
            self._busy = False
        if not accepted:
            return
        title, text = dialog.values()
        if tpl:
            tpl.title, tpl.text = title, text
        else:
            tpl = Template(title, text)
        try:
            self.store.save(tpl)
        except BrokenFile as e:
            self._broken(e)

    def remove(self, tpl: Template):
        box = QMessageBox(QMessageBox.Question, "Удалить шаблон", f"Удалить «{tpl.title}»?", parent=self)
        box.setWindowFlag(Qt.WindowStaysOnTopHint)
        yes = box.addButton("Удалить", QMessageBox.DestructiveRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        self._busy = True
        try:
            box.exec()
        finally:
            self._busy = False
        if box.clickedButton() is yes:
            try:
                self.store.delete(tpl)
            except BrokenFile as e:
                self._broken(e)

    def _broken(self, error: BrokenFile):
        box = QMessageBox(
            QMessageBox.Warning,
            "Шаблоны не сохранены",
            f"Не удалось прочитать файл шаблонов, поэтому он не тронут:\n{self.store.path}\n\n{error}\n\n"
            "Исправьте или удалите файл и повторите.",
            parent=self,
        )
        box.setWindowFlag(Qt.WindowStaysOnTopHint)
        self._busy = True
        try:
            box.exec()
        finally:
            self._busy = False

    def _flash(self, message: str):
        # the tab doubles as the status line
        self.tab.setText(message)
        self._toast.start()
