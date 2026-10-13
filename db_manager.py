import sqlite3
import os
import time
from pathlib import Path

DB_PATH = "bot_system.db"
VAULT_CONFIG_FILE = "security.vault"

class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token TEXT UNIQUE NOT NULL,
                    name TEXT,
                    username TEXT,
                    proxy TEXT,
                    is_active INTEGER DEFAULT 1
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    sender_name TEXT,
                    username TEXT,
                    is_blocked INTEGER DEFAULT 0,
                    is_pinned INTEGER DEFAULT 0,
                    is_muted INTEGER DEFAULT 0,
                    custom_note TEXT DEFAULT '',
                    first_seen INTEGER,
                    last_seen INTEGER,
                    UNIQUE(bot_id, chat_id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER,
                    is_outgoing INTEGER DEFAULT 0,
                    text TEXT,
                    media_type TEXT,
                    media_path TEXT,
                    file_name TEXT,
                    reply_to_text TEXT,
                    timestamp INTEGER,
                    is_read INTEGER DEFAULT 0,
                    reactions TEXT DEFAULT '',
                    is_deleted_locally INTEGER DEFAULT 0,
                    is_deleted_telegram INTEGER DEFAULT 0,
                    is_deleted_by_sender INTEGER DEFAULT 0,
                    is_edited INTEGER DEFAULT 0,
                    original_text TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS quick_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    text TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

            # Run migrations for chats table
            cursor.execute("PRAGMA table_info(chats)")
            cols = [row[1] for row in cursor.fetchall()]
            if "is_pinned" not in cols:
                cursor.execute("ALTER TABLE chats ADD COLUMN is_pinned INTEGER DEFAULT 0")
            if "is_muted" not in cols:
                cursor.execute("ALTER TABLE chats ADD COLUMN is_muted INTEGER DEFAULT 0")
            if "custom_note" not in cols:
                cursor.execute("ALTER TABLE chats ADD COLUMN custom_note TEXT DEFAULT ''")
            if "first_seen" not in cols:
                cursor.execute("ALTER TABLE chats ADD COLUMN first_seen INTEGER")
            if "last_seen" not in cols:
                cursor.execute("ALTER TABLE chats ADD COLUMN last_seen INTEGER")
            if "bio" not in cols:
                cursor.execute("ALTER TABLE chats ADD COLUMN bio TEXT DEFAULT ''")
            if "avatar_path" not in cols:
                cursor.execute("ALTER TABLE chats ADD COLUMN avatar_path TEXT DEFAULT ''")

            # Run migrations for messages table
            cursor.execute("PRAGMA table_info(messages)")
            msg_cols = [row[1] for row in cursor.fetchall()]
            if "media_type" not in msg_cols:
                cursor.execute("ALTER TABLE messages ADD COLUMN media_type TEXT")
            if "media_path" not in msg_cols:
                cursor.execute("ALTER TABLE messages ADD COLUMN media_path TEXT")
            if "file_name" not in msg_cols:
                cursor.execute("ALTER TABLE messages ADD COLUMN file_name TEXT")
            if "reply_to_text" not in msg_cols:
                cursor.execute("ALTER TABLE messages ADD COLUMN reply_to_text TEXT")
            if "is_read" not in msg_cols:
                cursor.execute("ALTER TABLE messages ADD COLUMN is_read INTEGER DEFAULT 0")
                cursor.execute("""
                    UPDATE messages SET is_read = 1
                    WHERE is_outgoing = 1 AND timestamp <= (
                        SELECT COALESCE(MAX(m2.timestamp), 0) FROM messages m2 
                        WHERE m2.bot_id = messages.bot_id AND m2.chat_id = messages.chat_id AND m2.is_outgoing = 0
                    )
                """)
            if "is_deleted_by_sender" not in msg_cols:
                cursor.execute("ALTER TABLE messages ADD COLUMN is_deleted_by_sender INTEGER DEFAULT 0")
            if "is_edited" not in msg_cols:
                cursor.execute("ALTER TABLE messages ADD COLUMN is_edited INTEGER DEFAULT 0")
            if "original_text" not in msg_cols:
                cursor.execute("ALTER TABLE messages ADD COLUMN original_text TEXT")
            if "reactions" not in msg_cols:
                cursor.execute("ALTER TABLE messages ADD COLUMN reactions TEXT DEFAULT ''")

            # Seed default quick replies if table empty
            cursor.execute("SELECT COUNT(*) as cnt FROM quick_replies")
            if cursor.fetchone()["cnt"] == 0:
                defaults = [
                    ("Karşılama", "Merhaba! Size nasıl yardımcı olabilirim?"),
                    ("Bekleme", "İletinizi aldım, en kısa sürede inceleyip dönüş yapacağım."),
                    ("Teşekkür", "Teşekkürler, iyi günler dilerim."),
                    ("Anonimlik Bildirimi", "Bu hat üzerinden iletileriniz anonim olarak işlenmektedir.")
                ]
                cursor.executemany("INSERT INTO quick_replies (title, text) VALUES (?, ?)", defaults)

            conn.commit()

    # --- BOT İŞLEMLERİ ---
    def add_bot(self, token: str, name: str, username: str, proxy: str = "") -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bots (token, name, username, proxy, is_active)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(token) DO UPDATE SET
                    name=excluded.name,
                    username=excluded.username,
                    proxy=excluded.proxy,
                    is_active=1
            """, (token, name, username, proxy))
            conn.commit()
            return cursor.lastrowid

    def get_bots(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bots ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def delete_bot(self, bot_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bots WHERE id = ?", (bot_id,))
            conn.commit()

    # --- SOHBET İŞLEMLERİ ---
    def get_or_create_chat(self, bot_id: int, chat_id: int, sender_name: str, username: str):
        now = int(time.time())
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chats (bot_id, chat_id, sender_name, username, is_blocked, is_pinned, is_muted, custom_note, first_seen, last_seen)
                VALUES (?, ?, ?, ?, 0, 0, 0, '', ?, ?)
                ON CONFLICT(bot_id, chat_id) DO UPDATE SET
                    sender_name=excluded.sender_name,
                    username=excluded.username,
                    last_seen=excluded.last_seen
            """, (bot_id, chat_id, sender_name, username, now, now))
            conn.commit()
            cursor.execute("SELECT * FROM chats WHERE bot_id = ? AND chat_id = ?", (bot_id, chat_id))
            return dict(cursor.fetchone())

    def get_chats_for_bot(self, bot_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM chats 
                WHERE bot_id = ? 
                ORDER BY is_pinned DESC, last_seen DESC, id DESC
            """, (bot_id,))
            return [dict(row) for row in cursor.fetchall()]

    def toggle_pin_chat(self, bot_id: int, chat_id: int, is_pinned: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE chats SET is_pinned = ? WHERE bot_id = ? AND chat_id = ?", (is_pinned, bot_id, chat_id))
            conn.commit()

    def toggle_block_chat(self, bot_id: int, chat_id: int, is_blocked: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE chats SET is_blocked = ? WHERE bot_id = ? AND chat_id = ?", (is_blocked, bot_id, chat_id))
            conn.commit()

    def set_chat_note(self, bot_id: int, chat_id: int, note: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE chats SET custom_note = ? WHERE bot_id = ? AND chat_id = ?", (note, bot_id, chat_id))
            conn.commit()

    def is_chat_blocked(self, bot_id: int, chat_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_blocked FROM chats WHERE bot_id = ? AND chat_id = ?", (bot_id, chat_id))
            row = cursor.fetchone()
            return bool(row["is_blocked"]) if row else False

    def update_chat_profile(self, bot_id: int, chat_id: int, bio: str = None, avatar_path: str = None,
                            sender_name: str = None, username: str = None, custom_note: str = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            params = []
            if bio is not None:
                updates.append("bio = ?")
                params.append(bio)
            if avatar_path is not None:
                updates.append("avatar_path = ?")
                params.append(avatar_path)
            if sender_name is not None and sender_name != "":
                updates.append("sender_name = ?")
                params.append(sender_name)
            if username is not None:
                updates.append("username = ?")
                params.append(username)
            if custom_note is not None:
                updates.append("custom_note = ?")
                params.append(custom_note)
            if updates:
                params.extend([bot_id, chat_id])
                cursor.execute(f"UPDATE chats SET {', '.join(updates)} WHERE bot_id = ? AND chat_id = ?", params)
                conn.commit()

    def get_chat(self, bot_id: int, chat_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM chats WHERE bot_id = ? AND chat_id = ?", (bot_id, chat_id))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_chat_media(self, bot_id: int, chat_id: int, media_type: str = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if media_type:
                cursor.execute("""
                    SELECT * FROM messages 
                    WHERE bot_id = ? AND chat_id = ? AND media_type = ? AND is_deleted_locally = 0
                    ORDER BY timestamp DESC
                """, (bot_id, chat_id, media_type))
            else:
                cursor.execute("""
                    SELECT * FROM messages 
                    WHERE bot_id = ? AND chat_id = ? AND media_type IS NOT NULL AND is_deleted_locally = 0
                    ORDER BY timestamp DESC
                """, (bot_id, chat_id))
            return [dict(row) for row in cursor.fetchall()]

    # --- MESAJ İŞLEMLERİ ---
    def save_message(self, bot_id: int, chat_id: int, message_id: int, is_outgoing: int,
                     text: str, media_type: str = None, media_path: str = None, file_name: str = None,
                     reply_to_text: str = None, timestamp: int = None, is_read: int = 0) -> int:
        if timestamp is None:
            timestamp = int(time.time())
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages 
                (bot_id, chat_id, message_id, is_outgoing, text, media_type, media_path, file_name, reply_to_text, timestamp, is_read, is_deleted_locally, is_deleted_telegram, is_deleted_by_sender, is_edited)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0)
            """, (bot_id, chat_id, message_id, is_outgoing, text, media_type, media_path, file_name, reply_to_text, timestamp, is_read))
            cursor.execute("UPDATE chats SET last_seen = ? WHERE bot_id = ? AND chat_id = ?", (timestamp, bot_id, chat_id))
            conn.commit()
            return cursor.lastrowid

    def mark_outgoing_messages_as_read(self, bot_id: int, chat_id: int, up_to_timestamp: int = None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if up_to_timestamp is not None:
                cursor.execute("""
                    UPDATE messages SET is_read = 1 
                    WHERE bot_id = ? AND chat_id = ? AND is_outgoing = 1 AND is_read = 0 AND timestamp <= ?
                """, (bot_id, chat_id, up_to_timestamp + 300))
            else:
                cursor.execute("""
                    UPDATE messages SET is_read = 1 
                    WHERE bot_id = ? AND chat_id = ? AND is_outgoing = 1 AND is_read = 0
                """, (bot_id, chat_id))
            conn.commit()

    def set_message_read(self, message_db_id: int, is_read: int = 1):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE messages SET is_read = ? WHERE id = ?", (is_read, message_db_id))
            conn.commit()

    def get_message(self, message_db_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM messages WHERE id = ?", (message_db_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_messages(self, bot_id: int, chat_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM messages 
                WHERE bot_id = ? AND chat_id = ? AND is_deleted_locally = 0
                ORDER BY timestamp ASC, id ASC
            """, (bot_id, chat_id))
            return [dict(row) for row in cursor.fetchall()]

    def update_message_text(self, message_db_id: int, new_text: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE messages SET text = ? WHERE id = ?", (new_text, message_db_id))
            conn.commit()

    def update_message_reaction(self, message_db_id: int, reaction: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE messages SET reactions = ? WHERE id = ?", (reaction, message_db_id))
            conn.commit()

    def update_message_reaction_by_telegram_id(self, bot_id: int, chat_id: int, message_id: int, reaction: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE messages SET reactions = ? 
                WHERE bot_id = ? AND chat_id = ? AND message_id = ?
            """, (reaction, bot_id, chat_id, message_id))
            conn.commit()

    def mark_message_edited_by_sender(self, bot_id: int, chat_id: int, message_id: int, new_text: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM messages WHERE bot_id = ? AND chat_id = ? AND message_id = ?",
                           (bot_id, chat_id, message_id))
            row = cursor.fetchone()
            if row:
                old_text = row["text"]
                orig = row["original_text"] or old_text
                cursor.execute("""
                    UPDATE messages 
                    SET text = ?, is_edited = 1, original_text = ? 
                    WHERE id = ?
                """, (new_text, orig, row["id"]))
                conn.commit()
                return row["id"]
            return None

    def mark_message_deleted_by_sender(self, message_db_id: int, is_deleted: int = 1):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE messages SET is_deleted_by_sender = ? WHERE id = ?", (is_deleted, message_db_id))
            conn.commit()

    def mark_message_deleted_locally(self, message_db_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE messages SET is_deleted_locally = 1 WHERE id = ?", (message_db_id,))
            conn.commit()

    def mark_message_deleted_telegram(self, message_db_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE messages SET is_deleted_telegram = 1, is_deleted_locally = 1 WHERE id = ?
            """, (message_db_id,))
            conn.commit()

    def clear_chat_history(self, bot_id: int, chat_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE messages SET is_deleted_locally = 1 WHERE bot_id = ? AND chat_id = ?", (bot_id, chat_id))
            conn.commit()

    def delete_entire_chat(self, bot_id: int, chat_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE bot_id = ? AND chat_id = ?", (bot_id, chat_id))
            cursor.execute("DELETE FROM chats WHERE bot_id = ? AND chat_id = ?", (bot_id, chat_id))
            conn.commit()

    # --- HIZLI YANITLAR ---
    def get_quick_replies(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM quick_replies ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def add_quick_reply(self, title: str, text: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO quick_replies (title, text) VALUES (?, ?)", (title, text))
            conn.commit()

    # --- UYGULAMA AYARLARI ---
    def get_setting(self, key: str, default: str = None) -> str:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row["value"]
            return default

    def set_setting(self, key: str, value: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()


class DatabaseSecurityManager:
    """Manages master password authentication and AES-256 database file encryption."""
    VAULT_TOKEN_MAGIC = b"ANONIM_TELEGRAM_VAULT_OK"

    def __init__(self, vault_path=VAULT_CONFIG_FILE, db_path=DB_PATH):
        self.vault_path = Path(vault_path)
        self.db_path = Path(db_path)
        self._derived_key = None

    def is_vault_initialized(self) -> bool:
        return self.vault_path.exists() and self.vault_path.stat().st_size >= 48

    def _derive_fernet_key(self, password: str, salt: bytes) -> bytes:
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        import base64
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8')))

    def setup_master_password(self, password: str):
        from cryptography.fernet import Fernet
        salt = os.urandom(16)
        key = self._derive_fernet_key(password, salt)
        fernet = Fernet(key)
        token = fernet.encrypt(self.VAULT_TOKEN_MAGIC)
        with open(self.vault_path, "wb") as f:
            f.write(salt + token)
        self._derived_key = key
        self.encrypt_database()

    def verify_password(self, password: str) -> bool:
        if not self.is_vault_initialized():
            return False
        from cryptography.fernet import Fernet
        try:
            with open(self.vault_path, "rb") as f:
                data = f.read()
            salt = data[:16]
            token = data[16:]
            key = self._derive_fernet_key(password, salt)
            fernet = Fernet(key)
            if fernet.decrypt(token) == self.VAULT_TOKEN_MAGIC:
                self._derived_key = key
                return True
        except Exception:
            pass
        return False

    def encrypt_database(self) -> bool:
        if not self._derived_key or not self.db_path.exists():
            return False
        from cryptography.fernet import Fernet
        try:
            with open(self.db_path, "rb") as f:
                plain_data = f.read()
            enc_data = Fernet(self._derived_key).encrypt(plain_data)
            enc_path = self.db_path.with_suffix(".db.enc")
            with open(enc_path, "wb") as f:
                f.write(enc_data)
            return True
        except Exception:
            return False

    def decrypt_database(self) -> bool:
        enc_path = self.db_path.with_suffix(".db.enc")
        if not self._derived_key or not enc_path.exists():
            return False
        from cryptography.fernet import Fernet
        try:
            with open(enc_path, "rb") as f:
                enc_data = f.read()
            plain_data = Fernet(self._derived_key).decrypt(enc_data)
            with open(self.db_path, "wb") as f:
                f.write(plain_data)
            return True
        except Exception:
            return False
