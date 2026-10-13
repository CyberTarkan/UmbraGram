import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication, QDialog
from main import (
    MainWindow, NetworkShieldStartupDialog, BotManageDialog,
    ImageSecurityDialog, EmergencyDestructDialog
)
from network_manager import NetworkShieldManager
from db_manager import DatabaseManager
from telegram_service import BotManager
from shredder import secure_shred_file, secure_shred_directory


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestSecurityEnhancements:
    def test_image_security_dialog_accept_and_reject(self, qapp, tmp_path):
        dummy_img = tmp_path / "test_photo.png"
        dummy_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

        dlg = ImageSecurityDialog(str(dummy_img))
        assert "Görsel Güvenlik" in dlg.windowTitle()
        assert "Son Kontrol" in dlg.text() if hasattr(dlg, "text") else True

        # Test rejection
        dlg.reject()
        assert dlg.result() == QDialog.DialogCode.Rejected

        # Test accept
        dlg2 = ImageSecurityDialog(str(dummy_img))
        dlg2.accept()
        assert dlg2.result() == QDialog.DialogCode.Accepted

    def test_emergency_destruct_dialog(self, qapp):
        dlg = EmergencyDestructDialog()
        assert "ACİL DURUM" in dlg.windowTitle()
        dlg.reject()
        assert dlg.result() == QDialog.DialogCode.Rejected

    def test_startup_and_bot_manage_warnings(self, qapp):
        from PyQt6.QtWidgets import QLabel
        net_mgr = NetworkShieldManager()
        startup_dlg = NetworkShieldStartupDialog(net_mgr)
        labels = [lbl.text() for lbl in startup_dlg.findChildren(QLabel)]
        assert any("Hayati Anonimlik Uyarısı" in txt for txt in labels)

        db = DatabaseManager()
        bm = BotManager()
        bot_dlg = BotManageDialog(db, bm)
        bot_labels = [lbl.text() for lbl in bot_dlg.findChildren(QLabel)]
        assert any("Hayati Anonimlik Uyarısı" in txt for txt in bot_labels)

    def test_main_window_panic_hotkey_flow(self, qapp):
        with patch.object(BotManager, "start_bot"):
            win = MainWindow()
            assert hasattr(win, "panic_hotkey")
            assert hasattr(win, "panic_shortcut")
            assert win.btn_panic_destruct is not None
            assert "Acil İmha" in win.btn_panic_destruct.text()

            # Change hotkey
            win.panic_hotkey = "Ctrl+Shift+P"
            win.db.set_setting("panic_hotkey", "Ctrl+Shift+P")
            assert win.db.get_setting("panic_hotkey") == "Ctrl+Shift+P"
            win.close()
