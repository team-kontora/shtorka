"""How the drawer looks: a single background colour sets the whole palette, the style sets the shape."""
from PySide6.QtGui import QColor

DEFAULT_COLOR = "#000000"
DEFAULT_STYLE = "flat"

COLORS = {
    "Чёрный": "#000000",
    "Ночной": "#17212b",
    "Синий": "#2b5278",
    "Зелёный": "#1f4d3a",
    "Бордовый": "#5a1e2c",
    "Белый": "#ffffff",
}

STYLES = {
    "flat": "Прямоугольная",
    "rounded": "Скруглённая",
}

RADIUS = 8

STYLESHEET = """
QWidget {{ color: {fg}; font-family: "Segoe UI"; font-size: 13px; }}
#tab, #panel, #panel QWidget, QDialog {{ background: {bg}; }}
#tab {{ font-size: 12px; font-weight: 600; }}
#row {{ padding: 0 12px; }}
#row:hover {{ background: {hover}; }}
#add {{ color: {muted}; text-align: left; padding: 0 12px; border: none; border-top: 1px solid {hover}; border-radius: 0; }}
#add:hover {{ color: {fg}; background: {hover}; }}
QLineEdit, QPlainTextEdit {{
    background: {field}; border: 1px solid {border}; border-radius: 6px; padding: 6px;
    selection-background-color: {selection}; selection-color: {fg};
}}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {focus}; }}
QPushButton {{ background: {button}; border: none; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ background: {button_hover}; }}
QMenu {{ background: {menu}; border: 1px solid {border}; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; }}
QMenu::item:selected {{ background: {button}; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 6px; }}
QScrollBar::handle {{ background: {button_hover}; border-radius: 3px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""

# only the bottom corners are rounded: the top edge sits flush with the top of Telegram's window;
# the open tab keeps square corners so that the list hangs from it without a notch
ROUNDED = """
#tab[open="false"], #panel, #add {{ border-bottom-left-radius: {r}px; border-bottom-right-radius: {r}px; }}
"""


def color(value) -> str:
    """The configured colour as #rrggbb, or the default if it is not a colour."""
    parsed = QColor(value) if isinstance(value, str) else QColor()
    return parsed.name() if parsed.isValid() else DEFAULT_COLOR


def style(value) -> str:
    return value if value in STYLES else DEFAULT_STYLE


def _mix(a: QColor, b: QColor, t: float) -> str:
    return QColor(*(round(x + (y - x) * t) for x, y in zip(a.getRgb()[:3], b.getRgb()[:3]))).name()


def stylesheet(background: str, shape: str) -> str:
    bg = QColor(color(background))
    # dark text on light backgrounds; the shades are steps from the background towards the text colour
    light = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue() > 150
    fg = QColor("#000000" if light else "#ffffff")
    sheet = STYLESHEET.format(
        bg=bg.name(),
        fg=fg.name(),
        menu=_mix(bg, fg, 0.067),
        field=_mix(bg, fg, 0.10),
        hover=_mix(bg, fg, 0.15),
        button=_mix(bg, fg, 0.165),
        border=_mix(bg, fg, 0.20),
        button_hover=_mix(bg, fg, 0.228),
        selection=_mix(bg, fg, 0.267),
        focus=_mix(bg, fg, 0.467),
        muted=_mix(bg, fg, 0.541),
    )
    if style(shape) == "rounded":
        sheet += ROUNDED.format(r=RADIUS)
    return sheet
