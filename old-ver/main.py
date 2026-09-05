import sys
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from app.main_window import MainWindow

app = QApplication(sys.argv)
font = QFont("Microsoft JhengHei UI", 10)
if font.exactMatch():
    app.setFont(font)
window = MainWindow()
window.show()
sys.exit(app.exec())
