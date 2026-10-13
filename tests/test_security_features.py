import os
import tempfile
from pathlib import Path
import pytest
from PyQt6.QtWidgets import QApplication

from db_manager import DatabaseSecurityManager
from telegram_service import strip_media_metadata
from main import sanitize_url, SafeUrlDialog, MasterPasswordSetupDialog, MasterPasswordUnlockDialog, MainWindow


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


class TestSecurityAndAnonymity:
    def test_database_security_manager_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault_file = Path(tmp_dir) / "test.vault"
            db_file = Path(tmp_dir) / "test.db"
            db_file.write_bytes(b"SQLITE_SAMPLE_DATABASE_DATA_12345")

            sec_mgr = DatabaseSecurityManager(vault_path=vault_file, db_path=db_file)
            assert sec_mgr.is_vault_initialized() is False

            # 1. Setup Master Password
            sec_mgr.setup_master_password("SuperSecretKey123!")
            assert sec_mgr.is_vault_initialized() is True

            # Encrypted file should be generated
            enc_file = db_file.with_suffix(".db.enc")
            assert enc_file.exists() is True
            assert enc_file.read_bytes() != b"SQLITE_SAMPLE_DATABASE_DATA_12345"

            # 2. Verify wrong & correct password
            assert sec_mgr.verify_password("WrongPassword") is False
            assert sec_mgr.verify_password("SuperSecretKey123!") is True

            # 3. Simulate restoring / decrypting on startup
            db_file.unlink()
            assert db_file.exists() is False
            assert sec_mgr.decrypt_database() is True
            assert db_file.exists() is True
            assert db_file.read_bytes() == b"SQLITE_SAMPLE_DATABASE_DATA_12345"

    def test_strip_media_metadata_pdf_and_mp3(self):
        # 1. PDF metadata stripping
        from PyPDF2 import PdfWriter, PdfReader
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_metadata({"/Author": "SecretAuthor", "/Producer": "SecretMachine"})
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name
            writer.write(f)

        try:
            clean_pdf_path = strip_media_metadata(pdf_path)
            assert os.path.exists(clean_pdf_path)
            reader = PdfReader(clean_pdf_path)
            # Author metadata must be absent
            meta = reader.metadata or {}
            assert meta.get("/Author") is None
        finally:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

        # 2. MP3 ID3 Tag stripping
        fake_mp3 = b"ID3\x03\x00\x00\x00\x00\x00\x04DATA" + b"AUDIO_STREAM_BYTES" + b"TAG" + b"T"*125
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            mp3_path = f.name
            f.write(fake_mp3)

        try:
            clean_mp3_path = strip_media_metadata(mp3_path)
            assert os.path.exists(clean_mp3_path)
            with open(clean_mp3_path, "rb") as cf:
                cleaned_bytes = cf.read()
            assert cleaned_bytes == b"AUDIO_STREAM_BYTES"
        finally:
            if os.path.exists(mp3_path):
                os.remove(mp3_path)

    def test_sanitize_url_tracking_removal(self):
        dirty_url = "https://example.com/item?id=99&utm_source=telegram&utm_medium=cpc&fbclid=AQb_123&igshid=xyz"
        clean = sanitize_url(dirty_url)
        assert "utm_source" not in clean
        assert "fbclid" not in clean
        assert "igshid" not in clean
        assert "id=99" in clean
        assert clean == "https://example.com/item?id=99"

    def test_safe_url_dialog_ui(self, qapp):
        dirty_url = "https://example.com/landing?utm_source=telegram&ref=partner"
        dlg = SafeUrlDialog(dirty_url)
        assert dlg.trackers_removed is True
        assert dlg.clean_url == "https://example.com/landing"

    def test_stealth_typing_toggle(self, qapp):
        from telegram_service import BotManager
        from unittest.mock import patch
        with patch.object(BotManager, "start_bot"):
            win = MainWindow()
            assert win.stealth_typing is False
            assert "Açık" in win.btn_stealth_mode.text()

            win.toggle_stealth_typing()
            assert win.stealth_typing is True
            assert "Gizli" in win.btn_stealth_mode.text()

            win.toggle_stealth_typing()
            assert win.stealth_typing is False
            assert "Açık" in win.btn_stealth_mode.text()
            win.close()
