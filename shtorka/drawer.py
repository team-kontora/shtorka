"""The drawer window: a tab over Telegram's title bar that drops a list of template names on hover."""
from PySide6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation, Signal
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

from . import tgwin
from .store import Store, Template

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

STYLE = """
QWidget { color: #ffffff; font-family: "Segoe UI"; font-size: 13px; }
#tab, #panel, #panel QWidget, QDialog { background: #000000; }
#tab { font-size: 12px; font-weight: 600; }
#row { padding: 0 12px; }
#row:hover { background: #262626; }
#add { color: #8a8a8a; text-align: left; padding: 0 12px; border: none; border-top: 1px solid #262626; border-radius: 0; }
#add:hover { color: #ffffff; background: #262626; }
QLineEdit, QPlainTextEdit {
    background: #1a1a1a; border: 1px solid #333333; border-radius: 6px; padding: 6px;
    selection-background-color: #444444;
}
QLineEdit:focus, QPlainTextEdit:focus { border-color: #777777; }
QPushButton { background: #2a2a2a; border: none; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { background: #3a3a3a; }
QMenu { background: #111111; border: 1px solid #333333; padding: 4px; }
QMenu::item { padding: 5px 18px; }
QMenu::item:selected { background: #2a2a2a; }
QScrollArea { border: none; }
QScrollBar:vertical { background: transparent; width: 6px; }
QScrollBar::handle { background: #3a3a3a; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


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


class Drawer(QWidget):
    def __init__(self, cfg: dict, store: Store):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.cfg = cfg
        self.store = store
        self._tg: tgwin.Window | None = None
        self._geometry = None
        self._open = False
        # a menu or dialog of ours is up: leave the drawer exactly as it is
        self._busy = False
        # after a paste the cursor has to leave before hovering opens the list again
        self._armed = True
        self._misses = 0
        self._count = 0
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
        self.setStyleSheet(STYLE)

        self.tab = Tab(TAB_TEXT)
        self.tab.drag.connect(lambda: self._tg and tgwin.drag(self._tg.hwnd))
        self.tab.maximize.connect(lambda: self._tg and tgwin.toggle_maximize(self._tg.hwnd))
        self.tab.setObjectName("tab")
        self.tab.setAlignment(Qt.AlignCenter)
        self.tab.setFixedHeight(TAB_HEIGHT)

        self.rows = QVBoxLayout()
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        holder = QWidget()
        holder.setLayout(self.rows)
        scroll = QScrollArea()
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
            self._geometry = None
            self._place()

    def _hide(self):
        self._geometry = None
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
        return float(TAB_HEIGHT + (min(self._count, MAX_ROWS) + 1) * ROW_HEIGHT)

    def _set_open(self, is_open: bool, animate: bool = True):
        self._open = is_open
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
        if geometry != self._geometry:
            self._geometry = geometry
            tgwin.move(int(self.winId()), *geometry)

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

    # --- templates -----------------------------------------------------------

    def refresh(self):
        while item := self.rows.takeAt(0):
            if widget := item.widget():
                widget.deleteLater()
        templates = self.store.load()
        self._count = len(templates)
        for tpl in templates:
            row = Row(tpl)
            row.copy.connect(self.copy)
            row.paste.connect(self.paste)
            row.menu.connect(self.show_menu)
            self.rows.addWidget(row)
        self.rows.addStretch(1)
        # the list height follows the number of templates
        self._set_open(self._open)

    def copy(self, tpl: Template):
        QGuiApplication.clipboard().setText(tpl.text)
        self._flash("Скопировано ✓")

    def paste(self, tpl: Template):
        QGuiApplication.clipboard().setText(tpl.text)
        if not self._tg:
            return
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
        self.store.save(tpl)

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
            self.store.delete(tpl)

    def _flash(self, message: str):
        # the tab doubles as the status line
        self.tab.setText(message)
        self._toast.start()
