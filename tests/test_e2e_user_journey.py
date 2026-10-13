import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Guarantee offscreen mode for headless PyQt6 execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PIL import Image
from PyQt6.QtCore import Qt, QPoint, QPointF, QTimer
from PyQt6.QtGui import QPixmap, QColor, QKeySequence
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QInputDialog, QFileDialog

from db_manager import DatabaseManager, DatabaseSecurityManager
from network_manager import NetworkShieldManager, ShieldMode
from spam_protector import SpamProtector
from telegram_service import BotManager
from text_neutralizer import TextNeutralizer
from main import (
    AudioPlayerWidget,
    BotManageDialog,
    EmergencyDestructDialog,
    ImageSecurityDialog,
    MainWindow,
    MasterPasswordDialog,
    MasterPasswordSetupDialog,
    MasterPasswordUnlockDialog,
    MessageBubbleWidget,
    NetworkShieldStartupDialog,
)


@pytest.fixture
def temp_environment():
    """Provides an isolated temporary directory, database, and vault."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        db_path = tmp_path / "test_journey.db"
        vault_path = tmp_path / "test_journey.vault"

        db_mgr = DatabaseManager(db_path=str(db_path))
        sec_mgr = DatabaseSecurityManager(vault_path=vault_path, db_path=db_path)
        net_mgr = NetworkShieldManager(mode=ShieldMode.DIRECT, is_frozen=True)

        yield {
            "dir": tmp_path,
            "db_path": db_path,
            "vault_path": vault_path,
            "db": db_mgr,
            "sec_mgr": sec_mgr,
            "net_mgr": net_mgr,
        }


@pytest.fixture
def sample_image(temp_environment):
    """Creates a temporary sample image for image security testing."""
    img_path = temp_environment["dir"] / "user_photo.png"
    img = Image.new("RGB", (200, 200), color=(73, 109, 137))
    img.save(img_path)
    return str(img_path)


@pytest.fixture
def sample_audio(temp_environment):
    """Creates a dummy audio file for player testing."""
    audio_path = temp_environment["dir"] / "voice_memo.ogg"
    audio_path.write_bytes(b"OggS_DUMMY_AUDIO_DATA_FOR_PLAYBACK_TEST")
    return str(audio_path)


class TestE2EUserJourney:
    """
    Comprehensive E2E User Journey simulation in offscreen mode.
    Validates the entire UX lifecycle:
    1. Master Password setup & unlock (MasterPasswordDialog)
    2. Network Shield startup selection (Tor, Hybrid, Proxy, Direct)
    3. Bot management dialog (Add, List, Delete)
    4. Chat list selection & search bar filtering
    5. Text input & stylometric neutralization (🪄 / Ctrl+Shift+N)
    6. Image security inspection dialog & attachment flow
    7. Reactions, reply, edit, and audio playback (AudioPlayerWidget)
    8. Emergency destruct dialog & global panic shortcut (isolated/mocked)
    9. Full uninterrupted integrated journey
    """

    # =========================================================================
    # Step 1: Master Password Setup & Unlock Lifecycle
    # =========================================================================
    def test_e2e_step1_master_password_lifecycle(self, qapp, temp_environment):
        sec_mgr = temp_environment["sec_mgr"]
        db_path = temp_environment["db_path"]
        db_path.write_bytes(b"SQLITE_FORMAT_TEST_BYTES")

        # 1. First-time setup: Dialog is presented because vault is uninitialized
        assert sec_mgr.is_vault_initialized() is False
        setup_dlg = MasterPasswordSetupDialog(sec_mgr)
        setup_dlg.show()
        assert setup_dlg.windowTitle() == "UmbraGram - Güvenlik Anahtarı Belirleme"

        # Alias verification
        assert MasterPasswordDialog is MasterPasswordSetupDialog

        # Test validation: Too short password (< 4 chars)
        setup_dlg.pwd_input.setText("123")
        setup_dlg.pwd_confirm.setText("123")
        setup_dlg.cb_confirm.setChecked(True)
        with patch.object(QMessageBox, "warning") as mock_warn:
            setup_dlg._save_password()
            mock_warn.assert_called_once()
            assert "en az 4 karakter" in mock_warn.call_args[0][2]

        # Test validation: Password mismatch
        setup_dlg.pwd_input.setText("SecretPass#2026")
        setup_dlg.pwd_confirm.setText("MismatchedPass#2026")
        with patch.object(QMessageBox, "warning") as mock_warn:
            setup_dlg._save_password()
            mock_warn.assert_called_once()
            assert "eşleşmiyor" in mock_warn.call_args[0][2]

        # Test validation: Checkbox not checked
        setup_dlg.pwd_input.setText("SecretPass#2026")
        setup_dlg.pwd_confirm.setText("SecretPass#2026")
        setup_dlg.cb_confirm.setChecked(False)
        with patch.object(QMessageBox, "warning") as mock_warn:
            setup_dlg._save_password()
            mock_warn.assert_called_once()
            assert "onay kutusunu" in mock_warn.call_args[0][2]

        # User correctly fills password and accepts
        setup_dlg.cb_confirm.setChecked(True)
        with patch.object(QMessageBox, "information") as mock_info:
            setup_dlg._save_password()
            mock_info.assert_called_once()
            assert setup_dlg.result() == QDialog.DialogCode.Accepted

        assert sec_mgr.is_vault_initialized() is True
        assert db_path.with_suffix(".db.enc").exists()

        # 2. Subsequent app launch: Unlock Dialog is presented
        unlock_dlg = MasterPasswordUnlockDialog(sec_mgr)
        unlock_dlg.show()
        assert unlock_dlg.windowTitle() == "UmbraGram - Kilitli Veritabanı"

        # Wrong password attempt
        unlock_dlg.pwd_input.setText("WrongPassword!")
        with patch.object(QMessageBox, "critical") as mock_err:
            unlock_dlg._try_unlock()
            mock_err.assert_called_once()
            assert "Hatalı şifre" in mock_err.call_args[0][2]
            assert unlock_dlg.result() != QDialog.DialogCode.Accepted

        # Correct password unlocks the database
        unlock_dlg.pwd_input.setText("SecretPass#2026")
        unlock_dlg._try_unlock()
        assert unlock_dlg.result() == QDialog.DialogCode.Accepted
        assert db_path.exists() is True
        assert db_path.read_bytes() == b"SQLITE_FORMAT_TEST_BYTES"

    # =========================================================================
    # Step 2: Network Shield Startup Dialog (Modes & Kill-Switch)
    # =========================================================================
    def test_e2e_step2_network_shield_startup_modes(self, qapp, temp_environment):
        net_mgr = NetworkShieldManager(is_frozen=True)
        dlg = NetworkShieldStartupDialog(net_mgr)
        dlg.show()
        assert dlg.windowTitle() == "UmbraGram - Ağ Güvenlik Kalkanı"

        # Default options check
        assert dlg.rb_hybrid.isChecked() is True
        assert dlg.cb_kill_switch.isChecked() is True
        assert dlg.cb_custom_proxy.isChecked() is False
        assert dlg.input_custom_proxy.isEnabled() is False

        # Toggle custom proxy checkbox enables input
        dlg.cb_custom_proxy.setChecked(True)
        assert dlg.input_custom_proxy.isEnabled() is True
        dlg.input_custom_proxy.setText("socks5://127.0.0.1:1080")

        # Test selecting Tor Only mode
        dlg.rb_tor.setChecked(True)
        with patch.object(net_mgr, "find_tor_executable", return_value="tor.exe"), \
             patch.object(net_mgr, "start_tor_process", return_value=(True, 9050, "Tor devrede")):
            dlg._try_connect()
            assert net_mgr.mode == ShieldMode.TOR
            assert net_mgr.is_frozen is False
            assert dlg.result() == QDialog.DialogCode.Accepted

        # Test selecting Proxy Only mode
        net_mgr.is_frozen = True
        dlg2 = NetworkShieldStartupDialog(net_mgr)
        dlg2.show()
        dlg2.rb_proxy.setChecked(True)
        dlg2.cb_custom_proxy.setChecked(False)
        with patch.object(net_mgr, "find_working_proxy", return_value={"proxy": "http://185.190.1.1:8080", "latency_ms": 120}):
            dlg2._try_connect()
            assert net_mgr.mode == ShieldMode.PROXY
            assert net_mgr.active_proxy == "http://185.190.1.1:8080"
            assert net_mgr.is_frozen is False
            assert dlg2.result() == QDialog.DialogCode.Accepted

        # Test selecting Hybrid mode
        net_mgr.is_frozen = True
        dlg3 = NetworkShieldStartupDialog(net_mgr)
        dlg3.show()
        dlg3.rb_hybrid.setChecked(True)
        dlg3.cb_custom_proxy.setChecked(False)
        with patch.object(net_mgr, "find_tor_executable", return_value="tor.exe"), \
             patch.object(net_mgr, "start_tor_process", return_value=(True, 9050, "Tor devrede")), \
             patch.object(net_mgr, "find_working_proxy", return_value={"proxy": "socks5://127.0.0.1:9050", "latency_ms": 95}):
            dlg3._try_connect()
            assert net_mgr.mode == ShieldMode.HYBRID
            assert net_mgr.is_frozen is False
            assert dlg3.result() == QDialog.DialogCode.Accepted

        # Test selecting Direct mode
        net_mgr.is_frozen = True
        dlg4 = NetworkShieldStartupDialog(net_mgr)
        dlg4.show()
        dlg4.rb_direct.setChecked(True)
        dlg4._try_connect()
        assert net_mgr.mode == ShieldMode.DIRECT
        assert net_mgr.is_frozen is False
        assert dlg4.result() == QDialog.DialogCode.Accepted

    # =========================================================================
    # Step 3: Bot Management Dialog (Add, List, Delete)
    # =========================================================================
    def test_e2e_step3_bot_management(self, qapp, temp_environment):
        db = temp_environment["db"]
        bm = BotManager(db_manager=db)
        dlg = BotManageDialog(db=db, bot_manager=bm)
        dlg.show()

        # Initially table is empty
        assert dlg.table.rowCount() == 0
        assert not dlg.empty_bots_lbl.isHidden()

        # Validation: empty token warning
        dlg.name_input.setText("Test Bot")
        dlg.token_input.setText("")
        with patch.object(QMessageBox, "warning") as mock_warn:
            dlg.add_bot()
            mock_warn.assert_called_once()
            assert "Lütfen bir Bot Token girin" in mock_warn.call_args[0][2]

        # Valid addition
        dlg.name_input.setText("Gizli Operasyon Botu")
        dlg.token_input.setText("123456789:ABCDefGhIjKlMnOpQrStUvWxYz")
        dlg.proxy_input.setText("socks5://127.0.0.1:9050")

        bot_updated_emitted = []
        dlg.bots_updated.connect(lambda: bot_updated_emitted.append(True))

        with patch.object(bm, "start_bot") as mock_start:
            dlg.add_bot()
            mock_start.assert_called_once_with(
                bot_id=1,
                token="123456789:ABCDefGhIjKlMnOpQrStUvWxYz",
                proxy="socks5://127.0.0.1:9050"
            )

        assert dlg.table.rowCount() == 1
        assert dlg.empty_bots_lbl.isHidden()
        assert dlg.table.item(0, 1).text() == "Gizli Operasyon Botu"
        assert dlg.table.item(0, 3).text() == "socks5://127.0.0.1:9050"
        assert len(bot_updated_emitted) == 1

        # Delete confirmation dialog
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
             patch.object(bm, "stop_bot") as mock_stop:
            dlg.delete_bot(1)
            mock_stop.assert_called_once_with(1)
            assert dlg.table.rowCount() == 0
            assert len(bot_updated_emitted) == 2

    # =========================================================================
    # Step 4: Chat Selection, Search Bar Typing & Filtering
    # =========================================================================
    def test_e2e_step4_chat_selection_and_search_filter(self, qapp, temp_environment):
        db = temp_environment["db"]
        net_mgr = temp_environment["net_mgr"]
        net_mgr.is_frozen = False

        bot_id = db.add_bot("TEST_BOT_TOKEN", "Anonim Terminal", "anonim_term")
        db.get_or_create_chat(bot_id, 1001, "Ajan Delta", "ajan_delta")
        db.set_chat_note(bot_id, 1001, "Saha Ekibi")

        db.get_or_create_chat(bot_id, 1002, "Muhbir Kripto", "kripto_01")
        db.set_chat_note(bot_id, 1002, "Kriptolu Kanal")

        db.get_or_create_chat(bot_id, 1003, "Zeynep Arslan", "zeynep_ars")
        db.set_chat_note(bot_id, 1003, "Genel Koordinatör")

        with patch.object(BotManager, "start_bot"):
            win = MainWindow(net_manager=net_mgr, db_manager=db)
            win.show()
            qapp.processEvents()

            assert win.current_bot_id == bot_id
            win.refresh_chats()
            assert win.chat_list_widget.count() == 3

            # Search Bar Typing (Ctrl+K or direct input)
            win.search_input.setText("Muhbir")
            qapp.processEvents()
            # Items matching: 1
            assert win.chat_list_widget.count() == 1
            assert win.left_empty_frame.isVisible() is False

            # Search with no match
            win.search_input.setText("OlmayanKisi404")
            qapp.processEvents()
            assert win.chat_list_widget.count() == 0
            assert win.left_empty_frame.isVisible() is True
            assert "eşleşen sohbet bulunamadı" in win.left_empty_label.text()

            # Clear search
            win.search_input.clear()
            qapp.processEvents()
            assert win.chat_list_widget.count() == 3
            assert win.left_empty_frame.isVisible() is False

            # Chat Selection: Click on "Ajan Delta" (1001)
            item_delta = None
            for i in range(win.chat_list_widget.count()):
                it = win.chat_list_widget.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == 1001:
                    item_delta = it
                    break
            assert item_delta is not None

            win.on_chat_selected(item_delta)
            qapp.processEvents()

            assert win.active_chat_id == 1001
            assert win.active_chat_name == "Ajan Delta"
            assert win.chat_title.text() == "Ajan Delta"
            assert win.chat_uname_label.text() == "@ajan_delta"
            assert win.note_label.text() == "📝 Saha Ekibi"
            assert win.id_badge_btn.text() == "ID: 1001 📋"
            assert "Ajan Delta kullanıcısına mesaj yazın" in win.msg_input.placeholderText()

            win.close()

    # =========================================================================
    # Step 5: Message Input & Stylometric Text Neutralization (🪄 / Ctrl+Shift+N)
    # =========================================================================
    def test_e2e_step5_text_neutralizer_workflow(self, qapp, temp_environment):
        db = temp_environment["db"]
        net_mgr = temp_environment["net_mgr"]
        net_mgr.is_frozen = False

        bot_id = db.add_bot("TEST_BOT_TOKEN", "Anonim Bot", "anonim_bot")
        db.get_or_create_chat(bot_id, 2001, "Hedef Kisi", "hedef_kisi")

        with patch.object(BotManager, "start_bot"):
            win = MainWindow(net_manager=net_mgr, db_manager=db)
            win.show()
            qapp.processEvents()

            # Select chat
            win.refresh_chats()
            item = win.chat_list_widget.item(0)
            win.on_chat_selected(item)

            # User writes highly identifiable/stylometric Turkish text:
            original_text = "Hocam vallahi bence durum vahim, aynen öyle yani bilmukabele arz ederim."
            win.msg_input.setPlainText(original_text)

            # Trigger neutralization via 🪄 button
            win.neutralize_input_text()
            neutralized_text = win.msg_input.toPlainText()

            assert neutralized_text != original_text
            # Stylometric neutralizer replaces slang/filler/archaisms with objective standard phrasing
            assert "vallahi" not in neutralized_text
            assert len(neutralized_text) > 0

            # Empty input edge case: no crash
            win.msg_input.clear()
            win.neutralize_input_text()
            assert win.msg_input.toPlainText() == ""

            win.close()

    # =========================================================================
    # Step 6: Image Attachment Flow & ImageSecurityDialog Inspection
    # =========================================================================
    def test_e2e_step6_image_security_and_attachment_flow(self, qapp, temp_environment, sample_image):
        db = temp_environment["db"]
        net_mgr = temp_environment["net_mgr"]
        net_mgr.is_frozen = False

        bot_id = db.add_bot("TEST_BOT_TOKEN", "Anonim Bot", "anonim_bot")
        chat_id = 3001
        db.get_or_create_chat(bot_id, chat_id, "Görsel Alıcısı", "alici_img")

        # 1. Directly test ImageSecurityDialog UI inspection
        dlg = ImageSecurityDialog(sample_image)
        dlg.show()
        assert dlg.windowTitle() == "Görsel Güvenlik Kontrolü"
        assert dlg.image_path == sample_image

        # 2. Test in MainWindow: User cancels inspection dialog
        with patch.object(BotManager, "start_bot"):
            win = MainWindow(net_manager=net_mgr, db_manager=db)
            win.show()
            qapp.processEvents()

            item = win.chat_list_widget.item(0)
            win.on_chat_selected(item)

            # User chooses file but cancels in the security warning dialog
            with patch.object(ImageSecurityDialog, "exec", return_value=QDialog.DialogCode.Rejected):
                win.set_file_attachment(sample_image)
                # Attachment should NOT be loaded
                assert win.selected_file_path is None
                assert win.attachment_bar.isVisible() is False

            # 3. User inspects, confirms and accepts security dialog
            with patch.object(ImageSecurityDialog, "exec", return_value=QDialog.DialogCode.Accepted):
                win.set_file_attachment(sample_image)
                # Attachment bar is now visible and EXIF sanitization flag indicated
                assert win.selected_file_path == sample_image
                assert win.attachment_bar.isVisible() is True
                assert "EXIF/Konum Temizlendi" in win.attachment_label.text()
                assert win.att_thumb_label.isVisible() is True

                # User types caption and sends
                win.msg_input.setPlainText("Güvenli denetlenen fotoğraf ektedir.")
                mock_worker = MagicMock()
                mock_worker.isRunning.return_value = True

                with patch.object(win.bot_manager, "get_worker", return_value=mock_worker):
                    win.send_or_save_message()
                    mock_worker.send_file_async.assert_called_once_with(
                        chat_id, sample_image, "Güvenli denetlenen fotoğraf ektedir.", None, None
                    )

                # Bars should be reset after transmission
                assert win.selected_file_path is None
                assert win.attachment_bar.isVisible() is False
                assert win.msg_input.toPlainText() == ""

            win.close()

    # =========================================================================
    # Step 7: Reactions, Reply, Edit, and AudioPlayerWidget
    # =========================================================================
    def test_e2e_step7_reactions_reply_edit_and_audio_player(self, qapp, temp_environment, sample_audio):
        db = temp_environment["db"]
        net_mgr = temp_environment["net_mgr"]
        net_mgr.is_frozen = False

        bot_id = db.add_bot("TEST_BOT_TOKEN", "Anonim Bot", "anonim_bot")
        chat_id = 4001
        db.get_or_create_chat(bot_id, chat_id, "Etkileşim Kullanıcısı", "interact_user")

        # Insert a message into DB
        msg_id_db = db.save_message(
            bot_id=bot_id,
            chat_id=chat_id,
            message_id=5001,
            is_outgoing=0,
            text="Görüşme detaylarını paylaşır mısınız?",
            timestamp=int(time.time())
        )
        msg_data = db.get_message(msg_id_db)

        with patch.object(BotManager, "start_bot"):
            win = MainWindow(net_manager=net_mgr, db_manager=db)
            win.show()
            qapp.processEvents()

            win.on_chat_selected(win.chat_list_widget.item(0))

            # --- A. Reaction ---
            mock_worker = MagicMock()
            mock_worker.isRunning.return_value = True
            with patch.object(win.bot_manager, "get_worker", return_value=mock_worker):
                win.on_reaction_requested(msg_data, "🔥")
                mock_worker.send_reaction_async.assert_called_once_with(chat_id, 5001, "🔥")

            updated_msg = db.get_message(msg_id_db)
            assert updated_msg["reactions"] == "🔥"

            # --- B. Reply Flow ---
            win.on_reply_requested(msg_data)
            assert win.action_preview_bar.isVisible() is True
            assert win.active_reply_msg == msg_data
            assert "↩️" in win.action_icon_label.text()

            # User writes reply
            win.msg_input.setPlainText("Detaylar şifreli olarak iletildi.")
            with patch.object(win.bot_manager, "get_worker", return_value=mock_worker):
                win.send_or_save_message()
                mock_worker.send_message_async.assert_called_once_with(
                    chat_id, "Detaylar şifreli olarak iletildi.", 5001, "Görüşme detaylarını paylaşır mısınız?"
                )

            assert win.active_reply_msg is None
            assert win.action_preview_bar.isVisible() is False

            # --- C. Edit Flow ---
            # Create an outgoing message
            out_id_db = db.save_message(
                bot_id=bot_id,
                chat_id=chat_id,
                message_id=6001,
                is_outgoing=1,
                text="İlk taslak metin",
                timestamp=int(time.time())
            )
            out_msg = db.get_message(out_id_db)

            win.on_edit_requested(out_msg)
            assert win.action_preview_bar.isVisible() is True
            assert win.active_edit_msg == out_msg
            assert "✏️" in win.action_icon_label.text()
            assert win.msg_input.toPlainText() == "İlk taslak metin"
            assert win.btn_send.text() == "Kaydet"

            # Edit and save
            win.msg_input.setPlainText("Düzeltilmiş ve onaylanmış metin")
            with patch.object(win.bot_manager, "get_worker", return_value=mock_worker):
                win.send_or_save_message()
                mock_worker.edit_message_async.assert_called_once_with(chat_id, 6001, "Düzeltilmiş ve onaylanmış metin")

            assert win.active_edit_msg is None
            assert win.btn_send.text() == "Gönder"
            assert db.get_message(out_id_db)["text"] == "Düzeltilmiş ve onaylanmış metin"

            # --- D. Audio Player Widget Interaction ---
            player_widget = AudioPlayerWidget(sample_audio)
            player_widget.show()
            assert player_widget.btn_play.text() == "▶"
            player_widget._init_player()

            # Toggle playback (play -> pause)
            from PyQt6.QtMultimedia import QMediaPlayer
            with patch.object(player_widget.player, "play") as mock_play:
                player_widget.toggle_playback()
                mock_play.assert_called_once()
                assert AudioPlayerWidget._active_player == player_widget

            with patch.object(player_widget.player, "playbackState", return_value=QMediaPlayer.PlaybackState.PlayingState), \
                 patch.object(player_widget.player, "pause") as mock_pause:
                player_widget.toggle_playback()
                mock_pause.assert_called_once()

            # Duration and position updates
            player_widget.on_duration_changed(45000) # 0:45
            player_widget.on_position_changed(15000) # 0:15
            assert player_widget.time_lbl.text() == "0:15 / 0:45"

            # Seeking
            player_widget.seek_position(30000)
            player_widget.on_position_changed(30000)
            assert player_widget.slider.value() == 30000
            assert player_widget.time_lbl.text() == "0:30 / 0:45"

            # Stop and release
            player_widget.stop_and_release()
            assert AudioPlayerWidget._active_player is None

            win.close()

    # =========================================================================
    # Step 8: Emergency Destruct Dialog & Panic Hotkey (Mock/Temp Safe)
    # =========================================================================
    def test_e2e_step8_emergency_destruct_dialog_and_shortcut(self, qapp, temp_environment):
        db = temp_environment["db"]
        net_mgr = temp_environment["net_mgr"]
        net_mgr.is_frozen = False

        # 1. Verify Dialog direct UI elements
        dlg = EmergencyDestructDialog()
        dlg.show()
        assert "ACİL DURUM İMHASI" in dlg.windowTitle()
        assert dlg.width() == 460
        assert dlg.height() == 240

        # 2. Verify MainWindow Integration
        with patch.object(BotManager, "start_bot"):
            win = MainWindow(net_manager=net_mgr, db_manager=db)
            win.show()
            qapp.processEvents()

            # Default hotkey
            assert win.panic_hotkey == "Ctrl+Alt+Shift+X"
            assert "Ctrl+Alt+Shift+X" in win.btn_panic_destruct.toolTip()

            # Case A: User cancels self-destruct dialog -> forensic wipe NOT executed
            with patch.object(EmergencyDestructDialog, "exec", return_value=QDialog.DialogCode.Rejected), \
                 patch("main.execute_emergency_self_destruct") as mock_wipe:
                win.trigger_emergency_self_destruct()
                mock_wipe.assert_not_called()

            # Case B: User confirms self-destruct dialog via panic button -> forensic wipe triggered
            with patch.object(EmergencyDestructDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
                 patch("main.execute_emergency_self_destruct") as mock_wipe:
                win.trigger_emergency_self_destruct()
                mock_wipe.assert_called_once()

            # Case C: Global hotkey triggered via shortcut activation signal
            with patch.object(EmergencyDestructDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
                 patch("main.execute_emergency_self_destruct") as mock_wipe:
                win.panic_shortcut.activated.emit()
                mock_wipe.assert_called_once()

            # Case D: Change panic hotkey through menu prompt
            with patch.object(QInputDialog, "getText", return_value=("Ctrl+Shift+Delete", True)), \
                 patch.object(QMessageBox, "information"):
                win.change_panic_hotkey()
                assert win.panic_hotkey == "Ctrl+Shift+Delete"
                assert win.db.get_setting("panic_hotkey") == "Ctrl+Shift+Delete"
                assert "Ctrl+Shift+Delete" in win.btn_panic_destruct.toolTip()

            win.close()

    # =========================================================================
    # Step 9: Full Integrated End-to-End User Journey (Continuous Flow)
    # =========================================================================
    def test_e2e_step9_full_integrated_journey(self, qapp, temp_environment, sample_image, sample_audio):
        """
        Simulates an entire continuous, realistic user session from cold launch:
        Cold Launch -> Master Password -> Shield Setup -> Add Bot -> Receive Chat ->
        Search Chat -> Neutralize Text -> Inspect/Send Image -> Play Audio ->
        Reply & React -> Panic Shortcut.
        """
        sec_mgr = temp_environment["sec_mgr"]
        db = temp_environment["db"]
        net_mgr = temp_environment["net_mgr"]

        # Phase 1: First startup setup master password
        setup_dlg = MasterPasswordSetupDialog(sec_mgr)
        setup_dlg.pwd_input.setText("Operasyon2026!")
        setup_dlg.pwd_confirm.setText("Operasyon2026!")
        setup_dlg.cb_confirm.setChecked(True)
        with patch.object(QMessageBox, "information"):
            setup_dlg._save_password()
        assert setup_dlg.result() == QDialog.DialogCode.Accepted

        # Phase 2: Network Shield selection (Direct mode for local offline execution)
        shield_dlg = NetworkShieldStartupDialog(net_mgr)
        shield_dlg.rb_direct.setChecked(True)
        shield_dlg._try_connect()
        assert shield_dlg.result() == QDialog.DialogCode.Accepted
        assert net_mgr.is_frozen is False

        # Phase 3: Launch Main Window & Add Bot
        with patch.object(BotManager, "start_bot"):
            win = MainWindow(net_manager=net_mgr, db_manager=db)
            win.show()
            qapp.processEvents()

            bot_dlg = BotManageDialog(db=db, bot_manager=win.bot_manager, parent=win)
            bot_dlg.name_input.setText("Gölge Bot")
            bot_dlg.token_input.setText("555123456:AAGolGeBotTokenSecret")
            bot_dlg.add_bot()
            assert bot_dlg.table.rowCount() == 1

            win.load_initial_bots()
            assert win.bot_selector.count() == 1
            current_bid = win.current_bot_id

            # Phase 4: Incoming messages from two contacts
            win.on_message_received({
                "bot_id": current_bid,
                "chat_id": 9001,
                "message_id": 11,
                "sender_name": "Ajan Alpha",
                "username": "agent_alpha",
                "text": "Paket teslim noktasına ulaştı.",
                "timestamp": int(time.time()),
                "is_outgoing": False
            })
            win.on_message_received({
                "bot_id": current_bid,
                "chat_id": 9002,
                "message_id": 12,
                "sender_name": "Muhbir Beta",
                "username": "informant_beta",
                "text": "Acil durum sinyali alındı.",
                "timestamp": int(time.time()),
                "is_outgoing": False
            })

            # Phase 5: Search & Select Chat
            win.search_input.setText("Alpha")
            qapp.processEvents()
            assert win.chat_list_widget.count() == 1

            win.search_input.clear()
            qapp.processEvents()
            assert win.chat_list_widget.count() == 2

            # Select Ajan Alpha
            item_alpha = None
            for i in range(win.chat_list_widget.count()):
                it = win.chat_list_widget.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == 9001:
                    item_alpha = it
                    break
            assert item_alpha is not None
            win.on_chat_selected(item_alpha)
            assert win.active_chat_id == 9001
            assert win.active_chat_name == "Ajan Alpha"

            # Phase 6: Write identifiable text and neutralize with 🪄
            raw_text = "Kanka lütfeeeen bişey söyler misin ya??? slm nbr bu arada!!"
            win.msg_input.setPlainText(raw_text)
            win.neutralize_input_text()
            neutralized = win.msg_input.toPlainText()
            assert "Kanka" not in neutralized
            assert "Lütfen" in neutralized
            assert "bir şey" in neutralized

            # Phase 7: Attach image with visual security inspection
            with patch.object(ImageSecurityDialog, "exec", return_value=QDialog.DialogCode.Accepted):
                win.set_file_attachment(sample_image)
                assert win.attachment_bar.isVisible() is True

            mock_worker = MagicMock()
            mock_worker.isRunning.return_value = True
            with patch.object(win.bot_manager, "get_worker", return_value=mock_worker):
                win.send_or_save_message()
                mock_worker.send_file_async.assert_called_once()

            # Phase 8: Play incoming audio report
            player = AudioPlayerWidget(sample_audio)
            player._init_player()
            with patch.object(player.player, "play"):
                player.toggle_playback()
                assert AudioPlayerWidget._active_player == player
            player.stop_and_release()
            assert AudioPlayerWidget._active_player is None

            # Phase 9: React to message and reply
            msg_to_react = db.get_messages(current_bid, 9001)[0]
            with patch.object(win.bot_manager, "get_worker", return_value=mock_worker):
                win.on_reaction_requested(msg_to_react, "👍")
                assert db.get_message(msg_to_react["id"])["reactions"] == "👍"

            # Phase 10: Emergency self-destruct simulation via shortcut
            with patch.object(EmergencyDestructDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
                 patch("main.execute_emergency_self_destruct") as mock_destruct:
                win.panic_shortcut.activated.emit()
                mock_destruct.assert_called_once()

            win.close()
