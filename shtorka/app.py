import ctypes
import sys

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QColorDialog, QDialog, QMenu, QSystemTrayIcon

from . import __version__, autostart, config, hotkey, theme, updater
from .drawer import Drawer
from .store import Store


def _icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#5288c1"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Segoe UI", 28, QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "Ш")
    painter.end()
    return QIcon(pixmap)


def _swatch(color: str) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor(color))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#808080"))
    painter.drawRect(0, 0, 15, 15)
    painter.end()
    return QIcon(pixmap)


def _look_menus(menu: QMenu, drawer: Drawer) -> None:
    """Tray submenus that pick the drawer's colour and style; every choice is saved to config.json."""
    cfg = drawer.cfg

    def apply(**values):
        cfg.update(values)
        drawer.apply_look()

    def choose(**values):
        apply(**values)
        config.save(**values)
        sync()

    colors = menu.addMenu("Цвет шторки")
    color_group = QActionGroup(colors)
    presets = {}
    for name, value in theme.COLORS.items():
        action = colors.addAction(_swatch(value), name, lambda v=value: choose(color=v))
        action.setCheckable(True)
        color_group.addAction(action)
        presets[value] = action
    colors.addSeparator()
    custom = colors.addAction("Другой цвет…")
    custom.setCheckable(True)
    color_group.addAction(custom)

    def pick_custom():
        before = theme.color(cfg["color"])
        dialog = QColorDialog(QColor(before))
        dialog.setWindowTitle("Цвет шторки")
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint)
        # the drawer shows the colour while it is being picked
        dialog.currentColorChanged.connect(lambda c: apply(color=c.name()))
        if dialog.exec() == QDialog.Accepted:
            choose(color=dialog.selectedColor().name())
        else:
            apply(color=before)
            sync()

    custom.triggered.connect(pick_custom)

    styles = menu.addMenu("Стиль шторки")
    style_group = QActionGroup(styles)
    shapes = {}
    for key, name in theme.STYLES.items():
        action = styles.addAction(name, lambda k=key: choose(style=k))
        action.setCheckable(True)
        style_group.addAction(action)
        shapes[key] = action

    def sync():
        color = theme.color(cfg["color"])
        presets.get(color, custom).setChecked(True)
        custom.setIcon(QIcon() if color in presets else _swatch(color))
        shapes[theme.style(cfg["style"])].setChecked(True)

    sync()


def _hotkey_action(menu: QMenu, drawer: Drawer) -> None:
    """Tray item that shows the hotkey and lets the user press another one; the choice is saved to config.json."""

    def label():
        value = drawer.cfg.get("hotkey")
        return f"Горячая клавиша: {value}…" if hotkey.parse(value) else "Горячая клавиша: выключена…"

    def choose():
        value = drawer.choose_hotkey()
        if value is not None:
            config.save(hotkey=value)
            action.setText(label())

    action = menu.addAction(label())
    action.triggered.connect(choose)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Shtorka")
    app.setApplicationDisplayName("Shtorka")
    app.setQuitOnLastWindowClosed(False)

    if updater.PORTABLE and updater.INSTALLED_EXE.exists():
        # this single-file copy has already moved to the installed app
        updater.launch(updater.INSTALLED_EXE)
        return 0

    config.BASE.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(config.BASE / "app.lock"))
    if not lock.tryLock(0):
        return 0
    # Setup looks for this mutex to know that the app is still running
    ctypes.windll.kernel32.CreateMutexW(None, False, "ShtorkaAppMutex")
    if updater.FROZEN and not updater.PORTABLE:
        autostart.follow_exe()

    cfg = config.load()
    store = Store()
    drawer = Drawer(cfg, store)
    # a run from source has nothing to update; the name keeps the updater alive while the app runs
    _update = updater.Updater(lock) if updater.FROZEN and cfg["auto_update"] else None

    menu = QMenu()
    _look_menus(menu, drawer)
    _hotkey_action(menu, drawer)
    menu.addSeparator()
    startup = QAction("Запускать вместе с Windows", menu, checkable=True, checked=autostart.is_enabled())
    startup.toggled.connect(autostart.set_enabled)
    menu.addAction(startup)
    menu.addSeparator()
    menu.addAction("Выход", app.quit)

    tray = QSystemTrayIcon(_icon())
    tray.setToolTip(f"Shtorka {__version__}")
    tray.setContextMenu(menu)
    tray.show()
    # Setup passes this on the first start: nothing else shows that the app is running
    if "--welcome" in sys.argv:
        tray.showMessage(
            "Shtorka запущена",
            "Откройте Telegram — вкладка «Шаблоны» появится на его заголовке. Настройки — в меню этого значка.",
            _icon(),
        )

    return app.exec()
