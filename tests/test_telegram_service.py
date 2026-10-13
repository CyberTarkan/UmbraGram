import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from db_manager import DatabaseManager
from spam_protector import SpamProtector
from telegram_service import (
    BotManager,
    BotWorker,
    FetchProfileWorker,
    SendActionWorker,
    strip_image_metadata,
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


class TestTelegramService:
    def test_strip_image_metadata(self):
        # 1. Test RGB JPEG
        temp_dir = tempfile.gettempdir()
        rgb_path = os.path.join(temp_dir, "test_rgb.jpg")
        img = Image.new("RGB", (50, 50), color="red")
        img.save(rgb_path, "JPEG")

        cleaned = strip_image_metadata(rgb_path)
        assert os.path.exists(cleaned)
        assert Path(cleaned).suffix.lower() == ".jpg"

        # 2. Test RGBA PNG
        rgba_png = os.path.join(temp_dir, "test_rgba.png")
        img_rgba = Image.new("RGBA", (50, 50), color=(255, 0, 0, 128))
        img_rgba.save(rgba_png, "PNG")

        cleaned_png = strip_image_metadata(rgba_png)
        assert os.path.exists(cleaned_png)
        assert Path(cleaned_png).suffix.lower() == ".png"

        # 3. Test RGBA saved as JPEG extension (edge case)
        rgba_jpg = os.path.join(temp_dir, "test_rgba_as_jpg.jpg")
        # Save as PNG first then rename
        img_rgba.save(rgba_png)
        with open(rgba_png, "rb") as f_in, open(rgba_jpg, "wb") as f_out:
            f_out.write(f_in.read())

        cleaned_rgba_jpg = strip_image_metadata(rgba_jpg)
        assert os.path.exists(cleaned_rgba_jpg)

        # 4. Non-image file
        txt_path = os.path.join(temp_dir, "test.txt")
        with open(txt_path, "w") as f:
            f.write("hello")
        assert strip_image_metadata(txt_path) == txt_path

    def test_send_action_worker_success(self):
        cb_results = []

        def callback(success, result, err):
            cb_results.append((success, result, err))

        worker = SendActionWorker(
            token="TEST_TOKEN",
            action="sendMessage",
            params={"chat_id": 123, "text": "hello"},
            callback=callback
        )

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 42}}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            worker.run()
            mock_post.assert_called_once()
            assert len(cb_results) == 1
            assert cb_results[0][0] is True
            assert cb_results[0][1]["message_id"] == 42
            assert cb_results[0][2] == ""

    def test_send_action_worker_api_error(self):
        cb_results = []

        def callback(success, result, err):
            cb_results.append((success, result, err))

        worker = SendActionWorker(
            token="TEST_TOKEN",
            action="sendMessage",
            params={"chat_id": 123, "text": "hello"},
            callback=callback
        )

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "description": "Chat not found"}

        with patch("requests.post", return_value=mock_resp):
            worker.run()
            assert len(cb_results) == 1
            assert cb_results[0][0] is False
            assert cb_results[0][2] == "Chat not found"

    def test_send_action_worker_network_exception(self):
        cb_results = []

        def callback(success, result, err):
            cb_results.append((success, result, err))

        worker = SendActionWorker(
            token="TEST_TOKEN",
            action="sendMessage",
            params={"chat_id": 123, "text": "hello"},
            callback=callback
        )

        with patch("requests.post", side_effect=Exception("Connection timed out")):
            worker.run()
            assert len(cb_results) == 1
            assert cb_results[0][0] is False
            assert "Connection timed out" in cb_results[0][2]

    def test_send_action_worker_file_upload_closes_handles(self):
        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.write(b"dummy image data")
        temp_file.close()

        cb_results = []
        worker = SendActionWorker(
            token="TEST_TOKEN",
            action="sendPhoto",
            params={"chat_id": 123},
            files={"photo": temp_file.name},
            callback=lambda s, r, e: cb_results.append((s, r, e))
        )

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 99}}

        with patch("requests.post", return_value=mock_resp):
            worker.run()
            assert cb_results[0][0] is True

        # Ensure file can be removed (i.e. handle closed!)
        try:
            os.remove(temp_file.name)
        except Exception as e:
            pytest.fail(f"File handle was not closed, could not delete temp file: {e}")

    def test_fetch_profile_worker(self):
        cb_results = []

        def callback(bot_id, chat_id, data):
            cb_results.append((bot_id, chat_id, data))

        worker = FetchProfileWorker(
            token="TEST_TOKEN",
            bot_id=1,
            chat_id=555,
            callback=callback
        )

        session_mock = MagicMock()
        # Mock getChat response
        get_chat_resp = MagicMock()
        get_chat_resp.json.return_value = {
            "ok": True,
            "result": {
                "first_name": "John",
                "last_name": "Doe",
                "username": "johndoe",
                "bio": "Software Engineer"
            }
        }
        # Mock getUserProfilePhotos response
        photos_resp = MagicMock()
        photos_resp.json.return_value = {"ok": True, "result": {"photos": []}}

        def session_get(url, **kwargs):
            if "getChat" in url:
                return get_chat_resp
            elif "getUserProfilePhotos" in url:
                return photos_resp
            return MagicMock()

        session_mock.get.side_effect = session_get

        with patch("requests.Session", return_value=session_mock):
            worker.run()
            assert len(cb_results) == 1
            assert cb_results[0][0] == 1
            assert cb_results[0][1] == 555
            profile = cb_results[0][2]
            assert profile["first_name"] == "John"
            assert profile["last_name"] == "Doe"
            assert profile["username"] == "johndoe"
            assert profile["bio"] == "Software Engineer"

    def test_bot_worker_token_verification(self, temp_db):
        db, _ = temp_db
        bot_id = db.add_bot("TEST_TOKEN", "Bot", "")
        worker = BotWorker(bot_id=bot_id, token="TEST_TOKEN", db_manager=db)

        status_events = []
        worker.status_changed.connect(lambda bid, online, info: status_events.append((bid, online, info)))

        # Test failure case
        session_mock = MagicMock()
        me_fail_resp = MagicMock()
        me_fail_resp.json.return_value = {"ok": False, "description": "Unauthorized"}
        session_mock.get.return_value = me_fail_resp

        with patch("requests.Session", return_value=session_mock):
            worker.run()
            assert len(status_events) == 1
            assert status_events[0] == (bot_id, False, "Unauthorized")

        # Test success case
        status_events.clear()
        me_ok_resp = MagicMock()
        me_ok_resp.json.return_value = {"ok": True, "result": {"username": "anonim_test_bot"}}

        # Stop loop after getMe
        def get_side_effect(url, **kwargs):
            if "getMe" in url:
                return me_ok_resp
            worker.stop()
            updates_resp = MagicMock()
            updates_resp.json.return_value = {"ok": False}
            return updates_resp

        session_mock.get.side_effect = get_side_effect

        with patch("requests.Session", return_value=session_mock):
            worker.run()
            assert any(evt[1] is True and "@anonim_test_bot" in evt[2] for evt in status_events)
            # Check DB updated with username
            bot_row = db.get_bots()[0]
            assert bot_row["username"] == "anonim_test_bot"

    def test_bot_worker_process_update_message(self, temp_db):
        db, _ = temp_db
        sp = SpamProtector(enabled=True)
        bot_id = db.add_bot("TEST_TOKEN", "Bot", "bot")
        worker = BotWorker(bot_id=bot_id, token="TEST_TOKEN", spam_protector=sp, db_manager=db)

        received_msgs = []
        worker.message_received.connect(lambda d: received_msgs.append(d))

        session_mock = MagicMock()
        msg_payload = {
            "message_id": 101,
            "date": 1700000000,
            "chat": {"id": 123456},
            "from": {"first_name": "Jane", "last_name": "Smith", "username": "janesmith"},
            "text": "Hello bot!"
        }

        with patch.object(worker, "fetch_user_profile_async") as mock_fetch:
            worker.process_update_message(session_mock, msg_payload)
            mock_fetch.assert_called_once_with(123456)
            assert len(received_msgs) == 1
            m = received_msgs[0]
            assert m["bot_id"] == bot_id
            assert m["chat_id"] == 123456
            assert m["message_id"] == 101
            assert m["sender_name"] == "Jane Smith"
            assert m["username"] == "janesmith"
            assert m["text"] == "Hello bot!"
            assert m["is_outgoing"] is False

    def test_bot_worker_process_blocked_and_spam(self, temp_db):
        db, _ = temp_db
        sp = SpamProtector(max_messages=1, window_seconds=5.0, enabled=True)
        bot_id = db.add_bot("TEST_TOKEN", "Bot", "bot")
        worker = BotWorker(bot_id=bot_id, token="TEST_TOKEN", spam_protector=sp, db_manager=db)

        # 1. Block user in DB
        db.get_or_create_chat(bot_id, 999, "BlockedUser", "b_u")
        db.toggle_block_chat(bot_id, 999, 1)

        received_msgs = []
        worker.message_received.connect(lambda d: received_msgs.append(d))

        session_mock = MagicMock()
        msg_payload = {
            "message_id": 1,
            "chat": {"id": 999},
            "from": {"first_name": "Blocked"},
            "text": "This should be ignored"
        }
        worker.process_update_message(session_mock, msg_payload)
        assert len(received_msgs) == 0

        # 2. Test spam detector trigger
        spam_events = []
        worker.spam_detected.connect(lambda bid, cid, r: spam_events.append((bid, cid, r)))

        normal_msg = {
            "message_id": 2,
            "chat": {"id": 888},
            "from": {"first_name": "Spammer"},
            "text": "Spam msg 1"
        }
        with patch.object(worker, "fetch_user_profile_async"):
            worker.process_update_message(session_mock, normal_msg)
            assert len(received_msgs) == 1

            # Second message rapidly -> triggers spam
            rapid_msg = {
                "message_id": 3,
                "chat": {"id": 888},
                "from": {"first_name": "Spammer"},
                "text": "Spam msg 2"
            }
            worker.process_update_message(session_mock, rapid_msg)
        assert len(spam_events) == 1
        assert spam_events[0][0] == bot_id
        assert spam_events[0][1] == 888
        assert "mola" in spam_events[0][2].lower()

    def test_bot_worker_process_edited_update(self, temp_db):
        db, _ = temp_db
        bot_id = db.add_bot("TEST_TOKEN", "Bot", "bot")
        db.get_or_create_chat(bot_id, 777, "User", "user")
        db.save_message(bot_id, 777, message_id=301, is_outgoing=0, text="Initial text")

        worker = BotWorker(bot_id=bot_id, token="TEST_TOKEN", db_manager=db)

        edited_events = []
        worker.message_edited_by_remote.connect(lambda d: edited_events.append(d))

        edited_payload = {
            "message_id": 301,
            "chat": {"id": 777},
            "text": "Edited text by sender"
        }
        worker.process_edited_update(edited_payload)

        assert len(edited_events) == 1
        assert edited_events[0]["message_id"] == 301
        assert edited_events[0]["new_text"] == "Edited text by sender"
        assert edited_events[0]["id"] is not None

        # Check in DB
        msg_in_db = db.get_message(edited_events[0]["id"])
        assert msg_in_db["text"] == "Edited text by sender"
        assert msg_in_db["is_edited"] == 1
        assert msg_in_db["original_text"] == "Initial text"

    def test_bot_worker_process_reaction_update(self, temp_db):
        db, _ = temp_db
        bot_id = db.add_bot("TEST_TOKEN", "Bot", "bot")
        db.get_or_create_chat(bot_id, 666, "User", "user")
        msg_id = db.save_message(bot_id, 666, message_id=401, is_outgoing=1, text="Nice bot")

        worker = BotWorker(bot_id=bot_id, token="TEST_TOKEN", db_manager=db)

        rx_events = []
        worker.message_reaction_received.connect(lambda d: rx_events.append(d))

        rx_payload = {
            "chat": {"id": 666},
            "message_id": 401,
            "new_reaction": [{"type": "emoji", "emoji": "👍"}]
        }
        worker.process_reaction_update(rx_payload)

        assert len(rx_events) == 1
        assert rx_events[0]["reaction"] == "👍"
        assert rx_events[0]["message_id"] == 401

        # Check DB updated reaction and marked outgoing message read
        msg_db = db.get_message(msg_id)
        assert msg_db["reactions"] == "👍"
        assert msg_db["is_read"] == 1

    def test_bot_manager_lifecycle_and_delegation(self, temp_db):
        db, _ = temp_db
        bm = BotManager(db_manager=db)

        # Start bot
        with patch.object(BotWorker, "start") as mock_start:
            bm.start_bot(bot_id=1, token="TOKEN_A", proxy=None)
            mock_start.assert_called_once()
            assert bm.get_worker(1) is not None

        # Send reaction delegation
        worker = bm.get_worker(1)
        with patch.object(worker, "send_reaction_async") as mock_rx:
            bm.send_reaction(1, 100, 200, "❤️")
            mock_rx.assert_called_once_with(100, 200, "❤️")

        # Send chat action delegation
        with patch.object(worker, "send_chat_action_async") as mock_action:
            bm.send_chat_action(1, 100, "typing")
            mock_action.assert_called_once_with(100, "typing")

        # Stop bot
        bm.stop_bot(1)
        assert bm.get_worker(1) is None
