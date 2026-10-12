import sys

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import autostart, config
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


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Shtorka")
    app.setApplicationDisplayName("Shtorka")
    app.setQuitOnLastWindowClosed(False)

    config.BASE.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(config.BASE / "app.lock"))
    if not lock.tryLock(0):
        return 0

    cfg = config.load()
    store = Store()
    drawer = Drawer(cfg, store)

    menu = QMenu()
    startup = QAction("Запускать вместе с Windows", menu, checkable=True, checked=autostart.is_enabled())
    startup.toggled.connect(autostart.set_enabled)
    menu.addAction(startup)
    menu.addSeparator()
    menu.addAction("Выход", app.quit)

    tray = QSystemTrayIcon(_icon())
    tray.setToolTip("Shtorka")
    tray.setContextMenu(menu)
    tray.show()

    return app.exec()
