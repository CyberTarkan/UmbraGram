import os
import sqlite3
import tempfile
import pytest
from db_manager import DatabaseManager


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


class TestDatabaseManager:
    def test_init_db_creates_tables_and_seeds(self, temp_db):
        db, path = temp_db
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row["name"] for row in cursor.fetchall()}
            assert {"bots", "chats", "messages", "quick_replies"}.issubset(tables)

            # Check seeded quick replies
            cursor.execute("SELECT COUNT(*) as cnt FROM quick_replies")
            assert cursor.fetchone()["cnt"] >= 4

    def test_migrations_on_legacy_db(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            # Create a legacy DB missing newer columns
            conn = sqlite3.connect(path)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    sender_name TEXT,
                    username TEXT,
                    is_blocked INTEGER DEFAULT 0,
                    UNIQUE(bot_id, chat_id)
                );
            """)
            c.execute("""
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER,
                    is_outgoing INTEGER DEFAULT 0,
                    text TEXT,
                    timestamp INTEGER,
                    is_deleted_locally INTEGER DEFAULT 0,
                    is_deleted_telegram INTEGER DEFAULT 0
                );
            """)
            conn.commit()
            conn.close()

            # Initialize DatabaseManager on this legacy DB
            db = DatabaseManager(db_path=path)

            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute("PRAGMA table_info(chats)")
                chat_cols = {row[1] for row in c.fetchall()}
                assert {"is_pinned", "is_muted", "custom_note", "first_seen", "last_seen", "bio", "avatar_path"}.issubset(chat_cols)

                c.execute("PRAGMA table_info(messages)")
                msg_cols = {row[1] for row in c.fetchall()}
                assert {"media_type", "media_path", "file_name", "reply_to_text", "is_read", "is_deleted_by_sender", "is_edited", "original_text", "reactions"}.issubset(msg_cols)
        finally:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def test_bot_crud(self, temp_db):
        db, _ = temp_db
        # Add new bot
        bot_id = db.add_bot(token="12345:ABCDEF", name="TestBot", username="test_bot", proxy="socks5://127.0.0.1:9050")
        assert bot_id is not None

        bots = db.get_bots()
        assert len(bots) == 1
        assert bots[0]["token"] == "12345:ABCDEF"
        assert bots[0]["name"] == "TestBot"
        assert bots[0]["username"] == "test_bot"
        assert bots[0]["proxy"] == "socks5://127.0.0.1:9050"
        assert bots[0]["is_active"] == 1

        # ON CONFLICT update bot
        db.add_bot(token="12345:ABCDEF", name="UpdatedBot", username="updated_bot", proxy="")
        bots_after = db.get_bots()
        assert len(bots_after) == 1
        assert bots_after[0]["name"] == "UpdatedBot"
        assert bots_after[0]["username"] == "updated_bot"

        # Delete bot
        db.delete_bot(bots_after[0]["id"])
        assert len(db.get_bots()) == 0

    def test_chat_crud_and_ordering(self, temp_db):
        db, _ = temp_db
        bot_id = db.add_bot(token="token1", name="Bot1", username="bot1")

        # Create chat 1
        chat1 = db.get_or_create_chat(bot_id=bot_id, chat_id=1001, sender_name="Alice", username="alice_u")
        assert chat1["chat_id"] == 1001
        assert chat1["sender_name"] == "Alice"
        assert chat1["first_seen"] is not None
        assert chat1["last_seen"] is not None
        first_seen_initial = chat1["first_seen"]

        # Re-fetch / conflict update for chat 1
        chat1_updated = db.get_or_create_chat(bot_id=bot_id, chat_id=1001, sender_name="Alice Wonder", username="alice_wonder")
        assert chat1_updated["sender_name"] == "Alice Wonder"
        assert chat1_updated["first_seen"] == first_seen_initial

        # Create chat 2
        chat2 = db.get_or_create_chat(bot_id=bot_id, chat_id=1002, sender_name="Bob", username="bob_u")

        # Test toggle pin
        db.toggle_pin_chat(bot_id=bot_id, chat_id=1002, is_pinned=1)
        chats = db.get_chats_for_bot(bot_id)
        assert len(chats) == 2
        # Pinned chat should come first
        assert chats[0]["chat_id"] == 1002
        assert chats[0]["is_pinned"] == 1

        # Test toggle block & is_chat_blocked
        assert db.is_chat_blocked(bot_id, 1001) is False
        db.toggle_block_chat(bot_id, 1001, 1)
        assert db.is_chat_blocked(bot_id, 1001) is True
        db.toggle_block_chat(bot_id, 1001, 0)
        assert db.is_chat_blocked(bot_id, 1001) is False

        # Test chat notes
        db.set_chat_note(bot_id, 1001, "Önemli Müşteri")
        chat1_fetch = db.get_chat(bot_id, 1001)
        assert chat1_fetch["custom_note"] == "Önemli Müşteri"

        # Test update_chat_profile
        db.update_chat_profile(bot_id, 1001, bio="Developer", avatar_path="/path/to/avatar.jpg", sender_name="Alice W.", username="alicew")
        chat1_fetch2 = db.get_chat(bot_id, 1001)
        assert chat1_fetch2["bio"] == "Developer"
        assert chat1_fetch2["avatar_path"] == "/path/to/avatar.jpg"
        assert chat1_fetch2["sender_name"] == "Alice W."
        assert chat1_fetch2["username"] == "alicew"

    def test_message_operations_and_flags(self, temp_db):
        db, _ = temp_db
        bot_id = db.add_bot(token="token1", name="Bot1", username="bot1")
        db.get_or_create_chat(bot_id, 1001, "Alice", "alice_u")

        # Save outgoing message
        msg1_id = db.save_message(
            bot_id=bot_id,
            chat_id=1001,
            message_id=50,
            is_outgoing=1,
            text="Merhaba Alice",
            timestamp=1000
        )
        assert msg1_id is not None

        # Verify last_seen was updated in chats table
        chat = db.get_chat(bot_id, 1001)
        assert chat["last_seen"] == 1000

        # Save incoming message with media
        msg2_id = db.save_message(
            bot_id=bot_id,
            chat_id=1001,
            message_id=51,
            is_outgoing=0,
            text="Selam!",
            media_type="photo",
            media_path="/downloads/bot_1/photo.jpg",
            file_name="photo.jpg",
            timestamp=1005
        )

        messages = db.get_messages(bot_id, 1001)
        assert len(messages) == 2
        assert messages[0]["id"] == msg1_id
        assert messages[1]["id"] == msg2_id

        # Test mark_outgoing_messages_as_read
        assert messages[0]["is_read"] == 0
        db.mark_outgoing_messages_as_read(bot_id, 1001, up_to_timestamp=1010)
        messages_after = db.get_messages(bot_id, 1001)
        assert messages_after[0]["is_read"] == 1

        # Test set_message_read manual toggle
        db.set_message_read(msg1_id, 0)
        assert db.get_message(msg1_id)["is_read"] == 0
        db.set_message_read(msg1_id, 1)
        assert db.get_message(msg1_id)["is_read"] == 1

        # Test update_message_text
        db.update_message_text(msg1_id, "Merhaba Alice (Düzenlendi)")
        assert db.get_message(msg1_id)["text"] == "Merhaba Alice (Düzenlendi)"

        # Test update_message_reaction
        db.update_message_reaction(msg1_id, "🔥")
        assert db.get_message(msg1_id)["reactions"] == "🔥"

        # Test mark_message_edited_by_sender
        res_edit = db.mark_message_edited_by_sender(bot_id, 1001, 51, "Selam yeni metin!")
        assert res_edit == msg2_id
        msg2_data = db.get_message(msg2_id)
        assert msg2_data["text"] == "Selam yeni metin!"
        assert msg2_data["is_edited"] == 1
        assert msg2_data["original_text"] == "Selam!"

        # Non-existent message edit returns None
        assert db.mark_message_edited_by_sender(bot_id, 1001, 9999, "None") is None

        # Test mark_message_deleted_by_sender
        db.mark_message_deleted_by_sender(msg2_id, 1)
        assert db.get_message(msg2_id)["is_deleted_by_sender"] == 1
        db.mark_message_deleted_by_sender(msg2_id, 0)
        assert db.get_message(msg2_id)["is_deleted_by_sender"] == 0

        # Test mark_message_deleted_locally
        db.mark_message_deleted_locally(msg1_id)
        # Deleted locally should not appear in get_messages
        messages_filtered = db.get_messages(bot_id, 1001)
        assert len(messages_filtered) == 1
        assert messages_filtered[0]["id"] == msg2_id

        # Test mark_message_deleted_telegram
        db.mark_message_deleted_telegram(msg2_id)
        assert len(db.get_messages(bot_id, 1001)) == 0
        msg2_refetch = db.get_message(msg2_id)
        assert msg2_refetch["is_deleted_telegram"] == 1
        assert msg2_refetch["is_deleted_locally"] == 1

    def test_chat_media_and_deletion(self, temp_db):
        db, _ = temp_db
        bot_id = db.add_bot("token1", "Bot1", "bot1")
        db.get_or_create_chat(bot_id, 2001, "User", "user")

        # Insert various media messages
        db.save_message(bot_id, 2001, 1, 0, "Photo msg", media_type="photo", media_path="p1.jpg")
        db.save_message(bot_id, 2001, 2, 0, "Doc msg", media_type="document", media_path="d1.pdf")
        db.save_message(bot_id, 2001, 3, 0, "Voice msg", media_type="voice", media_path="v1.ogg")
        db.save_message(bot_id, 2001, 4, 0, "Text only", media_type=None)

        all_media = db.get_chat_media(bot_id, 2001)
        assert len(all_media) == 3

        photos = db.get_chat_media(bot_id, 2001, media_type="photo")
        assert len(photos) == 1
        assert photos[0]["file_name"] is None or photos[0]["media_type"] == "photo"

        # Clear chat history (soft delete messages)
        db.clear_chat_history(bot_id, 2001)
        assert len(db.get_messages(bot_id, 2001)) == 0
        assert len(db.get_chat_media(bot_id, 2001)) == 0
        # Chat still exists
        assert db.get_chat(bot_id, 2001) is not None

        # Delete entire chat (hard delete messages and chat)
        db.delete_entire_chat(bot_id, 2001)
        assert db.get_chat(bot_id, 2001) is None
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) as cnt FROM messages WHERE bot_id = ? AND chat_id = ?", (bot_id, 2001))
            assert c.fetchone()["cnt"] == 0

    def test_quick_replies(self, temp_db):
        db, _ = temp_db
        initial_qr = db.get_quick_replies()
        assert len(initial_qr) >= 4
        assert any("Merhaba" in qr["text"] for qr in initial_qr)

        db.add_quick_reply("İndirim", "Özel kampanya kodu: YAZ2026")
        updated_qr = db.get_quick_replies()
        assert len(updated_qr) == len(initial_qr) + 1
        assert any(qr["title"] == "İndirim" for qr in updated_qr)

    def test_sql_injection_safety_and_unicode_handling(self, temp_db):
        db, _ = temp_db
        # Attempt injection in bot token and name
        malicious_input = "'; DROP TABLE messages; --"
        bot_id = db.add_bot(token=malicious_input, name="Hacker 🤠", username="hack_bot")
        assert bot_id is not None

        # Ensure messages table still exists
        chat = db.get_or_create_chat(bot_id, 9999, "Üser 🇹🇷 ' \" <script>", "user_uni")
        assert "Üser" in chat["sender_name"]

        # Insert massive text with unicode & emojis
        huge_text = ("🌟 Anonim Telegram Test Mesajı 🔥 " * 200) + malicious_input
        msg_id = db.save_message(bot_id, 9999, 1, 0, huge_text)
        fetched = db.get_message(msg_id)
        assert fetched["text"] == huge_text

        # Update chat profile with custom_note
        db.update_chat_profile(bot_id, 9999, bio="Bio with 'quotes'", custom_note="VIP Note ✨")
        chat_fetched = db.get_chat(bot_id, 9999)
        assert chat_fetched["custom_note"] == "VIP Note ✨"
        assert chat_fetched["bio"] == "Bio with 'quotes'"
