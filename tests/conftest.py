import os
import sys
import pytest

# Ensure Qt offscreen mode is set before any Qt imports
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # Clean teardown
    app.processEvents()
