import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Offscreen mode for PyQt6 headless automated testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PIL import Image
from PyQt6.QtCore import Qt, QPoint, QPointF, QUrl, QTimer
from PyQt6.QtGui import QPixmap, QColor, QMouseEvent, QKeyEvent
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QInputDialog

from db_manager import DatabaseManager
from spam_protector import SpamProtector
from telegram_service import BotManager
from main import (
    AudioPlayerWidget,
    BotManageDialog,
    ChatItemWidget,
    ChatInputEdit,
    ChatWallpaperWidget,
    EmojiPickerPopup,
    MainWindow,
    MessageBubbleWidget,
    TelegramAnimatedEmojiWidget,
    TelegramDeleteDialog,
    TelegramTickWidget,
    UserProfileDialog,
    is_emoji_only,
    make_circular_pixmap,
    make_clickable,
)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    yield db, path
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


class TestUIComponents:
    # 1. Helper Functions
    def test_make_circular_pixmap(self, qapp):
        # Null pixmap
        null_pix = QPixmap()
        res_null = make_circular_pixmap(null_pix, 40)
        assert res_null.isNull()

        # Square pixmap
        square_pix = QPixmap(100, 100)
        square_pix.fill(QColor("blue"))
        res_square = make_circular_pixmap(square_pix, 50)
        assert res_square.width() == 50
        assert res_square.height() == 50

        # Rectangular wide pixmap
        wide_pix = QPixmap(200, 100)
        wide_pix.fill(QColor("red"))
        res_wide = make_circular_pixmap(wide_pix, 60)
        assert res_wide.width() == 60
        assert res_wide.height() == 60

        # Rectangular tall pixmap
        tall_pix = QPixmap(100, 200)
        tall_pix.fill(QColor("green"))
        res_tall = make_circular_pixmap(tall_pix, 60)
        assert res_tall.width() == 60
        assert res_tall.height() == 60

    def test_make_clickable(self, qapp):
        from PyQt6.QtWidgets import QLabel
        lbl = QLabel("Click me")
        clicked = []
        make_clickable(lbl, lambda: clicked.append(True))
        assert lbl.cursor().shape() == Qt.CursorShape.PointingHandCursor

        # Simulate click
        event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(5, 5), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        lbl.mousePressEvent(event)
        assert clicked == [True]

    # 2. TelegramTickWidget
    def test_telegram_tick_widget(self, qapp):
        # Single tick (delivered / unread)
        tick_single = TelegramTickWidget(is_read=False)
        assert tick_single.is_read is False
        assert tick_single.width() == 13
        assert "✓ İletildi" in tick_single.toolTip()

        # Paint offscreen without error
        canvas = QPixmap(30, 30)
        tick_single.render(canvas)

        # Click event toggles signal
        clicked = []
        tick_single.clicked.connect(lambda: clicked.append(True))
        press_event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(5, 5), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        tick_single.mousePressEvent(press_event)
        assert clicked == [True]

        # Double tick (read / seen)
        tick_double = TelegramTickWidget(is_read=True)
        assert tick_double.is_read is True
        assert tick_double.width() == 18
        assert "✓✓ Görüldü" in tick_double.toolTip()
        tick_double.render(canvas)

        # Dynamic set_read toggle
        tick_single.set_read(True)
        assert tick_single.is_read is True
        assert tick_single.width() == 18
        assert "✓✓ Görüldü" in tick_single.toolTip()

    # 3. AudioPlayerWidget
    def test_audio_player_widget(self, qapp):
        temp_audio = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        temp_audio.write(b"OggS dummy audio data")
        temp_audio.close()

        try:
            player_widget = AudioPlayerWidget(temp_audio.name)
            assert player_widget.file_path == temp_audio.name
            assert player_widget.btn_play.text() == "▶"

            # Test seek position before playback initialization
            player_widget.seek_position(1500)
            assert player_widget.player is not None

            # Test play / pause toggle
            with patch.object(player_widget.player, "play") as mock_play, \
                 patch.object(player_widget.player, "pause") as mock_pause:
                player_widget.toggle_playback()
                mock_play.assert_called_once()
                assert AudioPlayerWidget._active_player == player_widget

            # Test duration & position changes
            player_widget.on_duration_changed(60000) # 1:00
            assert player_widget.duration_ms == 60000
            player_widget.on_position_changed(15000) # 0:15
            assert player_widget.time_lbl.text() == "0:15 / 1:00"

            # Test state changed
            from PyQt6.QtMultimedia import QMediaPlayer
            player_widget.on_state_changed(QMediaPlayer.PlaybackState.PlayingState)
            assert player_widget.btn_play.text() == "⏸"
            player_widget.on_state_changed(QMediaPlayer.PlaybackState.StoppedState)
            assert player_widget.btn_play.text() == "▶"

            # Test release
            player_widget.stop_and_release()
            assert AudioPlayerWidget._active_player is None
        finally:
            if os.path.exists(temp_audio.name):
                try:
                    os.remove(temp_audio.name)
                except Exception:
                    pass

    # 4. EmojiPickerPopup
    def test_emoji_picker_popup(self, qapp):
        popup = EmojiPickerPopup()
        selected = []
        popup.emoji_selected.connect(lambda e: selected.append(e))

        # Select first emoji
        popup._on_select("🔥")
        assert selected == ["🔥"]
        popup.close()

    # 5. ChatWallpaperWidget
    def test_chat_wallpaper_widget(self, qapp):
        wallpaper = ChatWallpaperWidget()
        wallpaper.resize(400, 300)
        canvas = QPixmap(400, 300)
        wallpaper.render(canvas)
        assert not canvas.isNull()

    # 6. MessageBubbleWidget
    def test_message_bubble_single_line_outgoing_and_incoming(self, qapp):
        # Single line outgoing
        msg_out = {
            "id": 1,
            "bot_id": 1,
            "chat_id": 100,
            "text": "Merhaba!",
            "is_outgoing": 1,
            "is_read": 0,
            "timestamp": int(time.time())
        }
        bubble_out = MessageBubbleWidget(msg_out)
        assert bubble_out.is_outgoing is True
        assert bubble_out.is_read is False
        assert bubble_out.tick_widget is not None
        assert bubble_out.tick_widget.is_read is False

        # Toggle read status via bubble
        toggle_signals = []
        bubble_out.request_toggle_read_status.connect(lambda mid, val: toggle_signals.append((mid, val)))
        bubble_out.toggle_read_status()
        assert bubble_out.is_read is True
        assert bubble_out.tick_widget.is_read is True
        assert toggle_signals == [(1, True)]

        # Double click triggers reply request
        reply_requests = []
        bubble_out.request_reply.connect(lambda data: reply_requests.append(data))
        dbl_click = QMouseEvent(QMouseEvent.Type.MouseButtonDblClick, QPointF(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        bubble_out.mouseDoubleClickEvent(dbl_click)
        assert len(reply_requests) == 1
        assert reply_requests[0]["id"] == 1

        # Single line incoming
        msg_in = {
            "id": 2,
            "bot_id": 1,
            "chat_id": 100,
            "text": "Selam!",
            "is_outgoing": 0,
            "is_read": 1,
            "timestamp": int(time.time())
        }
        bubble_in = MessageBubbleWidget(msg_in)
        assert bubble_in.is_outgoing is False
        assert bubble_in.tick_widget is None

    def test_message_bubble_rich_content_and_reactions(self, qapp):
        # Create temp image
        temp_img = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(temp_img.name)
        temp_img.close()

        try:
            msg_data = {
                "id": 10,
                "bot_id": 1,
                "chat_id": 200,
                "text": "Harika bir proje! Detaylar için https://telegram.org adresini ziyaret edin.",
                "media_type": "photo",
                "media_path": temp_img.name,
                "file_name": "photo.png",
                "reply_to_text": "Önceki yanıt metni",
                "is_edited": 1,
                "original_text": "Harika bir proje!",
                "is_deleted_by_sender": 1,
                "reactions": "👍",
                "is_outgoing": 1,
                "is_read": 1,
                "timestamp": int(time.time())
            }
            bubble = MessageBubbleWidget(msg_data)
            assert bubble.is_outgoing is True
            assert bubble.reaction == "👍"

            # Render offscreen
            canvas = QPixmap(500, 400)
            bubble.render(canvas)

            # Test reaction toggling
            rx_signals = []
            bubble.request_reaction.connect(lambda d, r: rx_signals.append((d, r)))
            bubble.toggle_reaction("👍") # removes reaction
            assert bubble.reaction == ""
            assert rx_signals == [(msg_data, "")]

            bubble.toggle_reaction("❤️") # adds new reaction
            assert bubble.reaction == "❤️"
            assert rx_signals[-1] == (msg_data, "❤️")

            # Test text copy
            bubble.copy_text()
            assert QApplication.clipboard().text() == msg_data["text"]

        finally:
            if os.path.exists(temp_img.name):
                try:
                    os.remove(temp_img.name)
                except Exception:
                    pass

    # 7. UserProfileDialog
    def test_user_profile_dialog(self, qapp, temp_db):
        db, _ = temp_db
        bm = BotManager(db_manager=db)
        bot_id = db.add_bot("TOKEN", "Bot", "bot")
        chat_id = 12345
        db.get_or_create_chat(bot_id, chat_id, "Ahmet Yilmaz", "ahmety")
        db.update_chat_profile(bot_id, chat_id, bio="Python developer", custom_note="VIP")

        # Add media for shared media tabs
        db.save_message(bot_id, chat_id, 1, 0, "Doc msg", media_type="document", file_name="resume.pdf", media_path="resume.pdf")
        db.save_message(bot_id, chat_id, 2, 0, "Audio msg", media_type="voice", file_name="voice.ogg", media_path="voice.ogg")

        dlg = UserProfileDialog(bot_id=bot_id, chat_id=chat_id, db=db, bot_manager=bm)
        assert dlg.name_lbl.text() == "Ahmet Yilmaz"
        assert dlg.uname_lbl.text() == "@ahmety"
        assert dlg.bio_content.text() == "Python developer"
        assert dlg.tabs.count() == 3

        # Test live profile update signal
        new_profile = {
            "sender_name": "Ahmet Yilmaz (Updated)",
            "username": "ahmet_new",
            "bio": "Senior Engineer",
            "avatar_path": ""
        }
        dlg.on_live_profile_fetched(bot_id, chat_id, new_profile)
        assert dlg.name_lbl.text() == "Ahmet Yilmaz (Updated)"
        assert dlg.uname_lbl.text() == "@ahmet_new"
        assert dlg.bio_content.text() == "Senior Engineer"

        # Test clean disconnect on done
        dlg.done(0)

    # 8. TelegramDeleteDialog & BotManageDialog
    def test_telegram_delete_dialog(self, qapp):
        dlg = TelegramDeleteDialog(target_user_name="Fatma Hanım")
        assert dlg.cb_everyone.isChecked() is True
        assert "Fatma Hanım" in dlg.cb_everyone.text()

        # Confirm
        dlg.on_confirm()
        assert dlg.delete_for_everyone is True

        # Uncheck and confirm
        dlg2 = TelegramDeleteDialog(target_user_name="Ali")
        dlg2.cb_everyone.setChecked(False)
        dlg2.on_confirm()
        assert dlg2.delete_for_everyone is False

    def test_bot_manage_dialog(self, qapp, temp_db):
        db, _ = temp_db
        bm = BotManager(db_manager=db)
        dlg = BotManageDialog(db=db, bot_manager=bm)

        # Empty initially
        assert dlg.table.rowCount() == 0

        # Add bot with empty token shows warning
        dlg.name_input.setText("Test")
        dlg.token_input.setText("")
        with patch.object(QMessageBox, "warning") as mock_warn:
            dlg.add_bot()
            mock_warn.assert_called_once()

        # Add valid bot
        dlg.name_input.setText("Anonim Bot 1")
        dlg.token_input.setText("BOT_TOKEN_123")
        with patch.object(bm, "start_bot") as mock_start:
            dlg.add_bot()
            mock_start.assert_called_once()

        assert dlg.table.rowCount() == 1
        assert dlg.table.item(0, 1).text() == "Anonim Bot 1"

        # Delete bot
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            dlg.delete_bot(int(dlg.table.item(0, 0).text()))
            assert dlg.table.rowCount() == 0

    # 9. ChatItemWidget & ChatInputEdit
    def test_chat_item_widget(self, qapp):
        item_w = ChatItemWidget(
            title="Mehmet",
            subtitle="Son iletilen mesaj...",
            is_pinned=True,
            custom_note="Acil",
            is_blocked=True,
            unread_count=3
        )
        canvas = QPixmap(300, 60)
        item_w.render(canvas)
        assert not canvas.isNull()

    def test_chat_input_edit(self, qapp):
        inp = ChatInputEdit()
        send_events = []
        cancel_events = []
        inp.send_requested.connect(lambda: send_events.append(True))
        inp.cancel_action_requested.connect(lambda: cancel_events.append(True))

        # Enter key triggers send
        key_enter = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        inp.keyPressEvent(key_enter)
        assert send_events == [True]

        # Shift+Enter does not trigger send
        key_shift_enter = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        inp.keyPressEvent(key_shift_enter)
        assert send_events == [True]

        # Escape key triggers cancel
        key_esc = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        inp.keyPressEvent(key_esc)
        assert cancel_events == [True]

    # 10. MainWindow Comprehensive End-to-End Test
    def test_main_window_full_workflow(self, qapp, temp_db):
        db, _ = temp_db
        bot_id = db.add_bot("VALID_BOT_TOKEN", "Ana Bot", "anabot")
        chat_id = 998877
        db.get_or_create_chat(bot_id, chat_id, "Zeynep", "zeynep_u")

        # Mock BotManager network calls during MainWindow initialization
        with patch.object(BotManager, "start_bot"):
            win = MainWindow()
            win.show()
            qapp.processEvents()
            # Replace win's internal DB with our test fixture DB
            win.db = db
            win.bot_manager.db = db
            win.load_initial_bots()

            # 1. Verify Bot Selection
            assert win.bot_selector.count() == 1
            assert win.current_bot_id == bot_id

            # 2. Select Chat
            win.refresh_chats()
            assert win.chat_list_widget.count() == 1
            item = win.chat_list_widget.item(0)
            win.on_chat_selected(item)

            assert win.active_chat_id == chat_id
            assert win.active_chat_name == "Zeynep"
            assert win.chat_title.text() == "Zeynep"
            assert win.chat_uname_label.text() == "@zeynep_u"
            assert win.btn_profile.isVisible() is True
            assert win.btn_pin.isVisible() is True

            # 3. Simulate Incoming Message
            incoming_data = {
                "bot_id": bot_id,
                "chat_id": chat_id,
                "message_id": 1001,
                "sender_name": "Zeynep",
                "username": "zeynep_u",
                "text": "Merhaba Anonim Bot!",
                "media_type": None,
                "media_path": None,
                "file_name": None,
                "reply_to_text": None,
                "timestamp": int(time.time()),
                "is_outgoing": False
            }
            win.on_message_received(incoming_data)
            assert win.messages_layout.count() >= 2  # Date separator + message bubble + stretch
            assert "🟢 çevrimiçi" in win.chat_status_label.text()

            # 4. In-Chat Search
            win.toggle_chat_search()
            assert win.chat_search_bar.isVisible() is True
            win.chat_search_input.setText("Merhaba")
            win.perform_chat_search()
            assert len(win.chat_search_matches) == 1
            assert win.chat_search_count_lbl.text() == "1 / 1"
            win.close_chat_search()
            assert win.chat_search_bar.isVisible() is False

            # 5. Typing Debounce
            win.last_typing_sent_time = 0
            win.msg_input.setPlainText("Yazıyorum...")
            # Triggers on_input_text_changed
            assert win.last_typing_sent_time > 0

            # 6. Outgoing Message Send Lifecycle
            win.msg_input.setPlainText("Cevap veriyorum!")
            mock_worker = MagicMock()
            mock_worker.isRunning.return_value = True
            with patch.object(win.bot_manager, "get_worker", return_value=mock_worker):
                win.send_or_save_message()
                mock_worker.send_message_async.assert_called_once_with(chat_id, "Cevap veriyorum!", None, None)

            # Simulate message_sent signal callback
            win.on_message_sent(
                bot_id=bot_id,
                chat_id=chat_id,
                text="Cevap veriyorum!",
                success=True,
                err="",
                msg_id=2001,
                media_type="",
                media_path="",
                reply_to_text=""
            )
            # Message bubble added for outgoing message
            outgoing_bubbles = [b for b in win.messages_container.findChildren(MessageBubbleWidget) if b.is_outgoing]
            assert len(outgoing_bubbles) == 1
            assert outgoing_bubbles[0].is_read is False

            # 7. Recipient Reaction marks outgoing message read
            win.on_message_reaction_received({
                "bot_id": bot_id,
                "chat_id": chat_id,
                "message_id": 2001,
                "reaction": "❤️"
            })
            # Verify outgoing bubble is marked read
            outgoing_bubbles_after = [b for b in win.messages_container.findChildren(MessageBubbleWidget) if b.is_outgoing]
            assert outgoing_bubbles_after[0].is_read is True

            # 8. File Attachment
            temp_doc = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
            temp_doc.write(b"Rapor")
            temp_doc.close()
            try:
                win.set_file_attachment(temp_doc.name)
                assert win.selected_file_path == temp_doc.name
                assert win.attachment_bar.isVisible() is True
                win.cancel_attachment()
                assert win.selected_file_path is None
                assert win.attachment_bar.isVisible() is False
            finally:
                if os.path.exists(temp_doc.name):
                    os.remove(temp_doc.name)

            # 9. Toggle Pin and Block
            win.toggle_active_chat_pin()
            assert "📌 Sabitlendi" in win.btn_pin.text()
            win.toggle_active_chat_pin()
            assert "📌 Sabitle" in win.btn_pin.text()

            win.toggle_active_chat_block()
            assert win.btn_block_toggle.text() == "Engeli Kaldır"
            win.toggle_active_chat_block()
            # 10. Note & Username Header Updates
            win.on_profile_note_updated("VIP Müşteri")
            assert win.note_label.text() == "📝 VIP Müşteri"
            assert win.note_label.isVisible() is True
            win.on_profile_note_updated("")
            assert win.note_label.isVisible() is False

            win.on_user_profile_fetched(bot_id, chat_id, {"username": ""})
            assert win.chat_uname_label.isVisible() is False
            win.on_user_profile_fetched(bot_id, chat_id, {"username": "zeynep_new"})
            assert win.chat_uname_label.text() == "@zeynep_new"
            assert win.chat_uname_label.isVisible() is True

            win.show_no_chat_selected_state()
            assert win.chat_title.text() == "Bir sohbet seçin"
            assert win.note_label.isVisible() is False
            assert win.chat_uname_label.isVisible() is False
            assert win.id_badge_btn.isVisible() is False

            # 11. Close Window
            from PyQt6.QtGui import QCloseEvent
            close_evt = QCloseEvent()
            win.closeEvent(close_evt)
            assert close_evt.isAccepted()

    def test_message_bubble_edge_cases(self):
        # 1. Video file bubble with caption
        temp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        temp_video.write(b"fake video")
        temp_video.close()
        try:
            msg_video = {
                "id": 88,
                "bot_id": 1,
                "chat_id": 100,
                "text": "Check out this video!",
                "media_type": "video",
                "media_path": temp_video.name,
                "file_name": "sample.mp4",
                "is_outgoing": 0
            }
            bubble_video = MessageBubbleWidget(msg_video)
            assert bubble_video.is_outgoing is False
            canvas = QPixmap(500, 300)
            bubble_video.render(canvas)

            # 2. Extremely long message text (e.g. 5,000 characters)
            long_text = "Uzun metin testi. " * 300
            msg_long = {
                "id": 89,
                "bot_id": 1,
                "chat_id": 100,
                "text": long_text,
                "is_outgoing": 1,
                "is_read": 1
            }
            bubble_long = MessageBubbleWidget(msg_long)
            assert bubble_long.is_outgoing is True
            bubble_long.render(canvas)

            # 3. Message with deleted file on disk
            msg_deleted_file = {
                "id": 90,
                "bot_id": 1,
                "chat_id": 100,
                "text": "Here was a file",
                "media_type": "document",
                "media_path": "non_existent_file.pdf",
                "file_name": "missing.pdf"
            }
            bubble_del = MessageBubbleWidget(msg_deleted_file)
            bubble_del.render(canvas)
        finally:
            if os.path.exists(temp_video.name):
                os.remove(temp_video.name)

    # 13. TelegramAnimatedEmojiWidget and Standalone Emoji MessageBubble
    def test_animated_emoji_bubble_and_widget(self, qapp):
        # Test helper function is_emoji_only
        assert is_emoji_only("😊") is True
        assert is_emoji_only("❤️") is True
        assert is_emoji_only("🔥") is True
        assert is_emoji_only("👍👍") is True
        assert is_emoji_only("🎉🎉🎉") is True
        assert is_emoji_only("👍👍👍👍") is False
        assert is_emoji_only("Merhaba 😊") is False
        assert is_emoji_only("test") is False
        assert is_emoji_only("") is False

        # Test widget direct instantiation, bounce, and render
        emoji_w = TelegramAnimatedEmojiWidget("🔥")
        assert emoji_w.emoji_text == "🔥"
        assert emoji_w.font_size == 46
        emoji_w.bounce()
        assert emoji_w.anim.state() == emoji_w.anim.State.Running

        # Test click signal
        clicks = []
        emoji_w.clicked.connect(lambda: clicks.append(1))
        click_evt = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(20, 20), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        emoji_w.mousePressEvent(click_evt)
        assert len(clicks) == 1

        canvas = QPixmap(100, 100)
        emoji_w.render(canvas)
        assert not canvas.isNull()

        # Test standalone emoji message bubble (outgoing)
        msg_emoji_out = {
            "id": 99,
            "bot_id": 1,
            "chat_id": 100,
            "text": "😊",
            "is_outgoing": 1,
            "is_read": 0,
            "timestamp": int(time.time())
        }
        bubble_emoji_out = MessageBubbleWidget(msg_emoji_out)
        assert bubble_emoji_out.emoji_widget is not None
        assert bubble_emoji_out.tick_widget is not None
        assert bubble_emoji_out.is_read is False

        # Toggle read status
        bubble_emoji_out.toggle_read_status()
        assert bubble_emoji_out.is_read is True
        assert bubble_emoji_out.tick_widget.is_read is True

        # Render outgoing emoji bubble
        canvas_bubble = QPixmap(120, 120)
        bubble_emoji_out.render(canvas_bubble)
        assert not canvas_bubble.isNull()

        # Test standalone emoji message bubble (incoming)
        msg_emoji_in = {
            "id": 100,
            "bot_id": 1,
            "chat_id": 100,
            "text": "❤️",
            "is_outgoing": 0,
            "is_read": 1,
            "timestamp": int(time.time())
        }
        bubble_emoji_in = MessageBubbleWidget(msg_emoji_in)
        assert bubble_emoji_in.emoji_widget is not None
        assert bubble_emoji_in.tick_widget is None
        bubble_emoji_in.render(canvas_bubble)
        assert not canvas_bubble.isNull()

        # Test standalone emoji with reaction badge
        msg_emoji_rx = {
            "id": 101,
            "bot_id": 1,
            "chat_id": 100,
            "text": "🔥",
            "reactions": "😃",
            "is_outgoing": 1,
            "is_read": 1,
            "timestamp": int(time.time())
        }
        bubble_emoji_rx = MessageBubbleWidget(msg_emoji_rx)
        assert bubble_emoji_rx.emoji_widget is not None
        assert bubble_emoji_rx.reaction == "😃"
        bubble_emoji_rx.render(canvas_bubble)
        assert not canvas_bubble.isNull()

    # 14. Reply quote click jump and message bubble flash highlight
    def test_reply_quote_click_jump_and_flash_highlight(self, qapp):
        # Create a bubble with reply_to_text containing an emoji
        msg_reply = {
            "id": 105,
            "bot_id": 1,
            "chat_id": 100,
            "text": "as",
            "reply_to_text": "😃",
            "is_outgoing": 1,
            "is_read": 1,
            "timestamp": int(time.time())
        }
        bubble = MessageBubbleWidget(msg_reply)
        assert bubble.reply_frame is not None

        # Verify reply click emits request_jump_to_message
        jump_targets = []
        bubble.request_jump_to_message.connect(lambda t: jump_targets.append(t))
        click_evt = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        bubble.reply_frame.mousePressEvent(click_evt)
        assert jump_targets == ["😃"]

        # Test flash_highlight animation
        bubble.flash_highlight()
        assert hasattr(bubble, "_flash_anim")
        assert bubble._flash_anim.state() == bubble._flash_anim.State.Running

        # Test step and completion
        bubble._on_flash_step(1.0)
        bubble._apply_normal_bubble_style()

        # Test flash_highlight on standalone emoji bubble as well
        msg_emoji = {"id": 106, "bot_id": 1, "chat_id": 100, "text": "😃", "is_outgoing": 0, "is_read": 1}
        bubble_emoji = MessageBubbleWidget(msg_emoji)
        assert bubble_emoji.is_standalone_emoji is True
        bubble_emoji.flash_highlight()
        bubble_emoji._on_flash_step(0.5)
        bubble_emoji._apply_normal_bubble_style()

        # Test MainWindow.on_jump_to_message_requested animated scroll
        win = MainWindow()
        win.current_bot_id = 1
        win.active_chat_id = 100
        win.append_message_bubble({"id": 107, "bot_id": 1, "chat_id": 100, "text": "Hedef mesaj"})
        win.append_message_bubble({"id": 108, "bot_id": 1, "chat_id": 100, "text": "Yanıtım", "reply_to_text": "Hedef mesaj"})
        win.on_jump_to_message_requested("Hedef mesaj")
        win.close()




