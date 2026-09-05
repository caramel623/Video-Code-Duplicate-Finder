from __future__ import annotations

# A modern, dark QSS theme applied to the whole application.
QSS = """
* {
    font-family: "Microsoft JhengHei UI", "Segoe UI", "Noto Sans CJK TC", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog {
    background: #1e2126;
}
QFrame#HeaderBar {
    background: #262a31;
    border-bottom: 1px solid #343a44;
}
QLabel { color: #e6e9ee; }
QLabel#RootLabel { color: #9aa2ad; font-size: 12px; }
QLabel#DetailTitle { font-size: 14px; font-weight: 700; color: #f2f4f8; }
QLabel#Muted { color: #9aa2ad; font-size: 12px; }

QPushButton {
    background: #3b82f6; color: #ffffff; border: none; border-radius: 8px;
    padding: 8px 16px;
}
QPushButton:hover { background: #4f8ff8; }
QPushButton:pressed { background: #2f6fe0; }
QPushButton:disabled { background: #3a4557; color: #8891a0; }
QPushButton[variant="secondary"] { background: #2c313a; color: #e6e9ee; border: 1px solid #3d4450; }
QPushButton[variant="secondary"]:hover { background: #343b46; }
QPushButton[variant="secondary"]:pressed { background: #262b33; }

QLineEdit {
    background: #23272e; border: 1px solid #3d4450; border-radius: 8px; padding: 7px 10px;
    color: #e6e9ee;
    selection-background-color: #3b82f6;
}
QLineEdit:focus { border: 1px solid #3b82f6; }

QSpinBox { background: #23272e; border: 1px solid #3d4450; border-radius: 6px; padding: 4px 8px; color: #e6e9ee; }

QCheckBox { spacing: 8px; color: #e6e9ee; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #4a525f; background: #23272e;
}
QCheckBox::indicator:checked { background: #3b82f6; border-color: #3b82f6; }

QGroupBox {
    background: #262a31; border: 1px solid #343a44; border-radius: 10px;
    margin-top: 14px; padding: 14px 12px 12px 12px; font-weight: 600; color: #e6e9ee;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #9aa2ad; }

QTableWidget {
    background: #23272e; border: 1px solid #343a44; border-radius: 10px;
    color: #e6e9ee;
    gridline-color: #2e333c;
    alternate-background-color: #262b33;
}
QTableWidget::item { padding: 6px; border: none; color: #e6e9ee; }
QTableWidget::item:selected { background: #2b4a80; color: #ffffff; }
QHeaderView::section {
    background: #2a2f38; color: #b7bdc7; border: none;
    border-bottom: 1px solid #343a44; padding: 9px; font-weight: 700;
}

QListWidget { background: #23272e; border: 1px solid #343a44; border-radius: 10px; color: #e6e9ee; }
QListWidget::item { padding: 8px 10px; border-radius: 6px; }
QListWidget::item:selected { background: #2b4a80; color: #ffffff; }

QMenu { background: #2a2f38; border: 1px solid #3d4450; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 22px 7px 14px; border-radius: 6px; color: #e6e9ee; }
QMenu::item:selected { background: #34507d; color: #ffffff; }
QMenu::separator { height: 1px; background: #3d4450; margin: 5px 8px; }

QTabWidget::pane { border: 1px solid #343a44; border-radius: 10px; top: -1px; background: #23272e; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: #262a31; color: #b7bdc7; padding: 8px 20px;
    border: 1px solid #343a44; border-bottom: none;
    border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px;
}
QTabBar::tab:selected { background: #23272e; color: #ffffff; font-weight: 700; }
QTabBar::tab:hover:!selected { background: #2c313a; }

QSplitter::handle { background: transparent; }

QStatusBar { background: #23272e; border-top: 1px solid #343a44; color: #9aa2ad; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: #454d59; border-radius: 6px; min-height: 26px; }
QScrollBar::handle:vertical:hover { background: #565f6c; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: #454d59; border-radius: 6px; min-width: 26px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QToolTip { background: #101216; color: #e6e9ee; border: 1px solid #3d4450; padding: 6px 9px; border-radius: 6px; }
"""


def apply_theme(app):
    app.setStyleSheet(QSS)