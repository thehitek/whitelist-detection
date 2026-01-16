from PySide6.QtWidgets import QApplication
from whitelist_checker import WhitelistChecker
import sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WhitelistChecker()
    window.show()
    sys.exit(app.exec())
