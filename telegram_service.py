import os
import time
import uuid
import requests
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal, QObject, QRunnable, QThreadPool

DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)


class SendActionWorker(QRunnable):
    def __init__(self, token: str, action: str, params: dict, files: dict = None, proxies: dict = None, callback=None, network_manager=None):
        super().__init__()
        self.token = token
        self.action = action
        self.params = params
        self.files = files
        self.proxies = proxies or {}
        self.callback = callback
        self.network_manager = network_manager

    def run(self):
        if self.network_manager and self.network_manager.is_frozen:
            if self.callback:
                self.callback(False, {}, "Ağ donduruldu (IP sızıntı koruması devrede)")
            return

        effective_proxies = self.proxies
        if self.network_manager:
            try:
                effective_proxies = self.network_manager.get_requests_proxies()
            except ConnectionAbortedError as e:
                if self.callback:
                    self.callback(False, {}, str(e))
                return
        url = f"https://api.telegram.org/bot{self.token}/{self.action}"
        file_handles = {}
        try:
            # Apply non-deterministic timing jitter to thwart traffic correlation attacks
            if self.network_manager:
                self.network_manager.apply_jitter()
            if self.files:
                for k, v in self.files.items():
                    if os.path.exists(v):
                        file_handles[k] = open(v, "rb")

            if file_handles:
                resp = requests.post(url, data=self.params, files=file_handles, proxies=effective_proxies, timeout=30)
            else:
                resp = requests.post(url, json=self.params, proxies=effective_proxies, timeout=15)

            data = resp.json()
            if data.get("ok"):
                if self.callback:
                    self.callback(True, data.get("result", {}), "")
            else:
                err = data.get("description", "Bilinmeyen hata")
                if self.callback:
                    self.callback(False, {}, err)
        except requests.exceptions.ProxyError as e:
            if self.network_manager and self.network_manager.kill_switch:
                self.network_manager.trigger_kill_switch(f"Proxy bağlantısı koptu: {e}")
            if self.callback:
                self.callback(False, {}, f"Kill-Switch devrede (Proxy koptu): {str(e)}")
        except Exception as e:
            if self.callback:
                self.callback(False, {}, str(e))
        finally:
            for h in file_handles.values():
                try:
                    h.close()
                except Exception:
                    pass


class FetchProfileWorker(QRunnable):
    def __init__(self, token: str, bot_id: int, chat_id: int, proxies: dict = None, callback=None, network_manager=None):
        super().__init__()
        self.token = token
        self.bot_id = bot_id
        self.chat_id = chat_id
        self.proxies = proxies or {}
        self.callback = callback
        self.network_manager = network_manager

    def run(self):
        if self.network_manager and self.network_manager.is_frozen:
            return
        effective_proxies = self.proxies
        if self.network_manager:
            try:
                effective_proxies = self.network_manager.get_requests_proxies()
            except ConnectionAbortedError:
                return

        profile_data = {
            "first_name": "",
            "last_name": "",
            "username": "",
            "bio": "",
            "avatar_path": ""
        }
        session = requests.Session()
        session.proxies = effective_proxies

        # 1. getChat (fetches name, username, bio)
        try:
            chat_url = f"https://api.telegram.org/bot{self.token}/getChat?chat_id={self.chat_id}"
            r = session.get(chat_url, timeout=10)
            res = r.json()
            if res.get("ok"):
                c = res.get("result", {})
                profile_data["first_name"] = c.get("first_name", "")
                profile_data["last_name"] = c.get("last_name", "")
                profile_data["username"] = c.get("username", "")
                profile_data["bio"] = c.get("bio", "")
                if "photo" in c and isinstance(c["photo"], dict):
                    profile_data["chat_photo_id"] = c["photo"].get("big_file_id") or c["photo"].get("small_file_id")
        except Exception:
            pass

        # 2. getUserProfilePhotos (downloads real profile photo)
        try:
            file_id = None
            photos_url = f"https://api.telegram.org/bot{self.token}/getUserProfilePhotos?user_id={self.chat_id}&limit=1"
            r = session.get(photos_url, timeout=10)
            res = r.json()
            if res.get("ok"):
                photos = res.get("result", {}).get("photos", [])
                if photos and len(photos) > 0:
                    best_photo = photos[0][-1]
                    file_id = best_photo.get("file_id")

            if not file_id and profile_data.get("chat_photo_id"):
                file_id = profile_data["chat_photo_id"]

            if file_id:
                info_url = f"https://api.telegram.org/bot{self.token}/getFile?file_id={file_id}"
                info_res = session.get(info_url, timeout=10).json()
                if info_res.get("ok"):
                    rem_path = info_res["result"].get("file_path")
                    if rem_path:
                        avatar_dir = DOWNLOADS_DIR / "avatars"
                        avatar_dir.mkdir(parents=True, exist_ok=True)
                        avatar_file = avatar_dir / f"user_{self.chat_id}.jpg"
                        download_url = f"https://api.telegram.org/file/bot{self.token}/{rem_path}"
                        with session.get(download_url, stream=True, timeout=20) as dl:
                            dl.raise_for_status()
                            with open(avatar_file, "wb") as f:
                                for chunk in dl.iter_content(chunk_size=8192):
                                    f.write(chunk)
                        profile_data["avatar_path"] = str(avatar_file.resolve())
        except Exception:
            pass

        if self.callback:
            self.callback(self.bot_id, self.chat_id, profile_data)


def strip_media_metadata(file_path: str) -> str:
    """Strips EXIF, GPS, author, device, and software metadata from outgoing media for anonymity."""
    try:
        ext = Path(file_path).suffix.lower()
        clean_dir = DOWNLOADS_DIR / "temp"
        clean_dir.mkdir(parents=True, exist_ok=True)
        clean_path = clean_dir / f"clean_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}{ext}"

        # 1. Images (EXIF, GPS, Camera Model, Software, Timestamps)
        if ext in ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'):
            from PIL import Image
            with Image.open(file_path) as img:
                if ext in ('.jpg', '.jpeg') and img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                clean_img = Image.new(img.mode, img.size)
                if img.mode == 'P' and img.getpalette():
                    clean_img.putpalette(img.getpalette())
                clean_img.paste(img)
                clean_img.save(clean_path)
                return str(clean_path.resolve())

        # 2. PDF Documents (Author, Creator, Producer, Creation Date)
        elif ext == '.pdf':
            from PyPDF2 import PdfReader, PdfWriter
            reader = PdfReader(file_path)
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            # Thoroughly clear internal PDF dictionary including library fingerprints
            if hasattr(writer, '_info') and writer._info:
                try:
                    writer._info.get_object().clear()
                except Exception:
                    pass
            with open(clean_path, "wb") as f:
                writer.write(f)
            return str(clean_path.resolve())

        # 3. MP3 Audio (ID3v1 and ID3v2 tags: Artist, Album, Title, Device encoder, APE tags)
        elif ext == '.mp3':
            with open(file_path, "rb") as f:
                data = f.read()
            # Strip multiple ID3v2 tags and handle footer flag
            while len(data) >= 10 and data[:3] == b'ID3':
                flags = data[5]
                has_footer = bool(flags & 0x10)
                size = ((data[6] & 0x7f) << 21) | ((data[7] & 0x7f) << 14) | ((data[8] & 0x7f) << 7) | (data[9] & 0x7f)
                tag_total = 10 + size + (10 if has_footer else 0)
                data = data[tag_total:]
            # Strip ID3v1 tags
            while len(data) >= 128 and data[-128:-125] == b'TAG':
                data = data[:-128]
            # Strip APE tags
            while len(data) >= 32 and data[-32:-24] == b'APETAGEX':
                data = data[:-32]

            with open(clean_path, "wb") as f:
                f.write(data)
            return str(clean_path.resolve())

    except Exception:
        pass
    return file_path


# Backward-compatible alias
strip_image_metadata = strip_media_metadata


class BotWorker(QThread):
    message_received = pyqtSignal(dict)
    message_sent = pyqtSignal(int, 'qint64', str, bool, str, 'qint64', str, str, str)
    message_edited = pyqtSignal(int, 'qint64', 'qint64', str, bool, str)
    message_edited_by_remote = pyqtSignal(dict)
    message_deleted = pyqtSignal(int, 'qint64', 'qint64', bool, str)
    profile_fetched = pyqtSignal(int, 'qint64', dict)  # bot_id, chat_id, profile_dict
    status_changed = pyqtSignal(int, bool, str)
    spam_detected = pyqtSignal(int, 'qint64', str)
    message_reaction_received = pyqtSignal(dict)

    def __init__(self, bot_id: int, token: str, proxy: str = None, spam_protector=None, db_manager=None, network_manager=None):
        super().__init__()
        self.bot_id = bot_id
        self.token = token
        self.proxy = proxy
        self.spam_protector = spam_protector
        self.db = db_manager
        self.network_manager = network_manager
        self.is_running = False
        self.proxies = {}
        if self.proxy:
            self.proxies = {"http": self.proxy, "https": self.proxy}

    def update_proxy(self, new_proxy: str = None):
        self.proxy = new_proxy
        self.proxies = {"http": new_proxy, "https": new_proxy} if new_proxy else {}
        if hasattr(self, "session") and self.session:
            self.session.proxies = self.proxies

    def run(self):
        self.is_running = True

        # Wait while network is frozen (IP leak protection)
        while self.network_manager and self.network_manager.is_frozen:
            if not self.is_running:
                return
            self.msleep(200)

        session = requests.Session()
        session.proxies = self.proxies
        self.session = session

        # 1. Verify token
        try:
            if self.network_manager:
                try:
                    session.proxies = self.network_manager.get_requests_proxies()
                except ConnectionAbortedError as e:
                    self.status_changed.emit(self.bot_id, False, f"Bağlantı Hatası: {str(e)}")
                    return
            me_resp = session.get(f"https://api.telegram.org/bot{self.token}/getMe", timeout=10)
            me_data = me_resp.json()
            if not me_data.get("ok"):
                self.status_changed.emit(self.bot_id, False, me_data.get("description", "Geçersiz Token"))
                return
            username = me_data["result"].get("username", "")
            if self.db and username:
                with self.db.get_connection() as conn:
                    conn.cursor().execute("UPDATE bots SET username = ? WHERE id = ?", (username, self.bot_id))
                    conn.commit()
            self.status_changed.emit(self.bot_id, True, f"@{username}")
        except requests.exceptions.ProxyError as e:
            if self.network_manager and self.network_manager.kill_switch:
                self.network_manager.trigger_kill_switch(f"Token doğrulamada proxy koptu: {e}")
            self.status_changed.emit(self.bot_id, False, f"Bağlantı Hatası: {str(e)}")
            return
        except Exception as e:
            self.status_changed.emit(self.bot_id, False, f"Bağlantı Hatası: {str(e)}")
            return

        # 2. Long-polling Loop
        offset = 0
        while self.is_running:
            if self.network_manager and self.network_manager.is_frozen:
                self.msleep(200)
                continue
            try:
                if self.network_manager:
                    try:
                        session.proxies = self.network_manager.get_requests_proxies()
                    except ConnectionAbortedError:
                        self.msleep(200)
                        continue
                params = {"timeout": 20, "offset": offset}
                resp = session.get(f"https://api.telegram.org/bot{self.token}/getUpdates", params=params, timeout=25)
                data = resp.json()
                if not data.get("ok"):
                    continue

                for update in data.get("result", []):
                    offset = max(offset, update["update_id"] + 1)
                    if "message" in update:
                        self.process_update_message(session, update["message"])
                    elif "edited_message" in update:
                        self.process_edited_update(update["edited_message"])
                    elif "message_reaction" in update:
                        self.process_reaction_update(update["message_reaction"])

            except requests.exceptions.Timeout:
                continue
            except (requests.exceptions.ProxyError, requests.exceptions.SSLError) as e:
                if self.network_manager and self.network_manager.kill_switch:
                    self.network_manager.trigger_kill_switch(f"Polling sırasında proxy koptu: {e}")
                if self.is_running:
                    self.msleep(1000)
            except requests.exceptions.RequestException:
                if self.is_running:
                    self.msleep(3000)
            except Exception:
                if self.is_running:
                    self.msleep(1000)

        self.status_changed.emit(self.bot_id, False, "Durduruldu")

    def process_edited_update(self, msg: dict):
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        message_id = msg.get("message_id")
        new_text = msg.get("text") or msg.get("caption") or ""

        if not chat_id or not message_id:
            return

        db_id = None
        if self.db:
            db_id = self.db.mark_message_edited_by_sender(self.bot_id, chat_id, message_id, new_text)

        self.message_edited_by_remote.emit({
            "bot_id": self.bot_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "new_text": new_text,
            "id": db_id
        })

    def process_reaction_update(self, rx: dict):
        chat = rx.get("chat", {})
        chat_id = chat.get("id")
        message_id = rx.get("message_id")
        new_reactions = rx.get("new_reaction", [])
        emoji = ""
        if new_reactions and isinstance(new_reactions, list):
            emoji = new_reactions[-1].get("emoji", "")
        if chat_id:
            if self.db:
                self.db.mark_outgoing_messages_as_read(self.bot_id, chat_id)
                if message_id:
                    self.db.update_message_reaction_by_telegram_id(self.bot_id, chat_id, message_id, emoji)
            self.message_reaction_received.emit({
                "bot_id": self.bot_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": emoji
            })

    def process_update_message(self, session: requests.Session, msg: dict):
        chat = msg.get("chat", {})
        sender = msg.get("from", {})
        chat_id = chat.get("id")
        message_id = msg.get("message_id")
        date_ts = msg.get("date", int(time.time()))

        if not chat_id:
            return

        if self.db and self.db.is_chat_blocked(self.bot_id, chat_id):
            return

        first_name = sender.get("first_name", "Kullanıcı")
        last_name = sender.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip()
        username = sender.get("username", "")

        text = msg.get("text") or msg.get("caption") or ""
        media_type = None
        file_id = None
        file_name = None

        if "photo" in msg and msg["photo"]:
            media_type = "photo"
            photo_obj = msg["photo"][-1]
            file_id = photo_obj["file_id"]
            file_name = f"photo_{message_id}_{int(time.time())}.jpg"
        elif "document" in msg:
            media_type = "document"
            doc_obj = msg["document"]
            file_id = doc_obj.get("file_id")
            file_name = doc_obj.get("file_name", f"doc_{message_id}")
        elif "voice" in msg:
            media_type = "voice"
            file_id = msg["voice"].get("file_id")
            file_name = f"voice_{message_id}.ogg"
        elif "video" in msg:
            media_type = "video"
            file_id = msg["video"].get("file_id")
            file_name = msg["video"].get("file_name", f"video_{message_id}.mp4")

        reply_to_text = None
        if "reply_to_message" in msg:
            rep = msg["reply_to_message"]
            reply_to_text = rep.get("text") or rep.get("caption") or "[Medya]"

        media_group_id = msg.get("media_group_id")

        if self.spam_protector:
            is_spam, is_permanent, reason = self.spam_protector.check_incoming(
                bot_id=self.bot_id,
                chat_id=chat_id,
                is_media=bool(media_type),
                media_group_id=media_group_id,
                text=text
            )
            if is_spam:
                if is_permanent and self.db:
                    self.db.toggle_block_chat(self.bot_id, chat_id, 1)
                self.spam_detected.emit(self.bot_id, chat_id, reason)
                return

        media_path = None
        if file_id:
            media_path = self.download_telegram_file(session, file_id, file_name)

        if text or media_path:
            self.fetch_user_profile_async(chat_id)
            self.message_received.emit({
                "bot_id": self.bot_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "sender_name": full_name or "Anonim",
                "username": username,
                "text": text,
                "media_type": media_type,
                "media_path": media_path,
                "file_name": file_name,
                "reply_to_text": reply_to_text,
                "timestamp": date_ts,
                "is_outgoing": False
            })

    def download_telegram_file(self, session: requests.Session, file_id: str, file_name: str) -> str:
        try:
            bot_folder = DOWNLOADS_DIR / f"bot_{self.bot_id}"
            bot_folder.mkdir(parents=True, exist_ok=True)
            local_path = bot_folder / file_name

            file_info_url = f"https://api.telegram.org/bot{self.token}/getFile?file_id={file_id}"
            info_resp = session.get(file_info_url, timeout=15).json()
            if not info_resp.get("ok"):
                return None

            rem_path = info_resp["result"].get("file_path")
            if not rem_path:
                return None

            download_url = f"https://api.telegram.org/file/bot{self.token}/{rem_path}"
            with session.get(download_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            return str(local_path.resolve())
        except Exception:
            return None

    def stop(self):
        self.is_running = False
        if hasattr(self, 'session') and self.session:
            try:
                self.session.close()
            except Exception:
                pass

    def send_message_async(self, chat_id: int, text: str, reply_to_message_id: int = None, reply_preview_text: str = None):
        params = {"chat_id": chat_id, "text": text}
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id

        def cb(success, result, err):
            msg_id = result.get("message_id", 0) if success else 0
            self.message_sent.emit(self.bot_id, chat_id, text, success, err, msg_id, "", "", reply_preview_text or "")

        worker = SendActionWorker(
            token=self.token,
            action="sendMessage",
            params=params,
            proxies=self.proxies,
            callback=cb,
            network_manager=self.network_manager
        )
        QThreadPool.globalInstance().start(worker)

    def send_file_async(self, chat_id: int, file_path: str, caption: str = "", reply_to_message_id: int = None, reply_preview_text: str = None):
        # Strip metadata from any media or document
        upload_path = strip_media_metadata(file_path)
        action = "sendPhoto" if file_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else "sendDocument"
        field = "photo" if action == "sendPhoto" else "document"

        params = {"chat_id": chat_id, "caption": caption}
        if reply_to_message_id:
            params["reply_to_message_id"] = reply_to_message_id

        def cb(success, result, err):
            msg_id = result.get("message_id", 0) if success else 0
            media_type = "photo" if action == "sendPhoto" else "document"
            self.message_sent.emit(self.bot_id, chat_id, caption, success, err, msg_id, media_type, file_path, reply_preview_text or "")

        worker = SendActionWorker(
            token=self.token,
            action=action,
            params=params,
            files={field: upload_path},
            proxies=self.proxies,
            callback=cb,
            network_manager=self.network_manager
        )
        QThreadPool.globalInstance().start(worker)

    def edit_message_async(self, chat_id: int, message_id: int, new_text: str):
        def cb(success, result, err):
            self.message_edited.emit(self.bot_id, chat_id, message_id, new_text, success, err)

        worker = SendActionWorker(
            token=self.token,
            action="editMessageText",
            params={"chat_id": chat_id, "message_id": message_id, "text": new_text},
            proxies=self.proxies,
            callback=cb,
            network_manager=self.network_manager
        )
        QThreadPool.globalInstance().start(worker)

    def delete_message_async(self, chat_id: int, message_id: int):
        def cb(success, result, err):
            self.message_deleted.emit(self.bot_id, chat_id, message_id, success, err)

        worker = SendActionWorker(
            token=self.token,
            action="deleteMessage",
            params={"chat_id": chat_id, "message_id": message_id},
            proxies=self.proxies,
            callback=cb,
            network_manager=self.network_manager
        )
        QThreadPool.globalInstance().start(worker)

    def fetch_user_profile_async(self, chat_id: int):
        def cb(bot_id, c_id, p_data):
            f_name = p_data.get("first_name", "")
            l_name = p_data.get("last_name", "")
            full_name = f"{f_name} {l_name}".strip()
            p_data["sender_name"] = full_name
            if self.db:
                self.db.update_chat_profile(
                    bot_id=bot_id,
                    chat_id=c_id,
                    bio=p_data.get("bio"),
                    avatar_path=p_data.get("avatar_path"),
                    sender_name=full_name or None,
                    username=p_data.get("username")
                )
            self.profile_fetched.emit(bot_id, c_id, p_data)

        worker = FetchProfileWorker(
            token=self.token,
            bot_id=self.bot_id,
            chat_id=chat_id,
            proxies=self.proxies,
            callback=cb,
            network_manager=self.network_manager
        )
        QThreadPool.globalInstance().start(worker)

    def send_reaction_async(self, chat_id: int, message_id: int, emoji: str):
        reactions = [{"type": "emoji", "emoji": emoji}] if emoji else []
        worker = SendActionWorker(
            token=self.token,
            action="setMessageReaction",
            params={"chat_id": chat_id, "message_id": message_id, "reaction": reactions},
            proxies=self.proxies,
            callback=None,
            network_manager=self.network_manager
        )
        QThreadPool.globalInstance().start(worker)

    def send_chat_action_async(self, chat_id: int, action: str = "typing"):
        worker = SendActionWorker(
            token=self.token,
            action="sendChatAction",
            params={"chat_id": chat_id, "action": action},
            proxies=self.proxies,
            callback=None,
            network_manager=self.network_manager
        )
        QThreadPool.globalInstance().start(worker)


class BotManager(QObject):
    message_received = pyqtSignal(dict)
    message_sent = pyqtSignal(int, 'qint64', str, bool, str, 'qint64', str, str, str)
    message_edited = pyqtSignal(int, 'qint64', 'qint64', str, bool, str)
    message_edited_by_remote = pyqtSignal(dict)
    message_deleted = pyqtSignal(int, 'qint64', 'qint64', bool, str)
    profile_fetched = pyqtSignal(int, 'qint64', dict)
    status_changed = pyqtSignal(int, bool, str)
    spam_detected = pyqtSignal(int, 'qint64', str)
    message_reaction_received = pyqtSignal(dict)

    def __init__(self, spam_protector=None, db_manager=None, network_manager=None):
        super().__init__()
        self.spam_protector = spam_protector
        self.db = db_manager
        self.network_manager = network_manager
        self.workers = {}

    def set_network_manager(self, network_manager):
        self.network_manager = network_manager
        for w in self.workers.values():
            w.network_manager = network_manager

    def freeze_all(self):
        if self.network_manager:
            self.network_manager.freeze_traffic()

    def unfreeze_all(self, new_proxy: str = None):
        if self.network_manager:
            self.network_manager.unfreeze_traffic()
        for w in self.workers.values():
            w.update_proxy(new_proxy)

    def start_bot(self, bot_id: int, token: str, proxy: str = None):
        self.stop_bot(bot_id)
        effective_proxy = proxy
        if not effective_proxy and self.network_manager:
            effective_proxy = self.network_manager.get_proxy_url()
        worker = BotWorker(
            bot_id=bot_id,
            token=token,
            proxy=effective_proxy,
            spam_protector=self.spam_protector,
            db_manager=self.db,
            network_manager=self.network_manager
        )
        worker.message_received.connect(self.message_received.emit)
        worker.message_sent.connect(self.message_sent.emit)
        worker.message_edited.connect(self.message_edited.emit)
        worker.message_edited_by_remote.connect(self.message_edited_by_remote.emit)
        worker.message_deleted.connect(self.message_deleted.emit)
        worker.profile_fetched.connect(self.profile_fetched.emit)
        worker.status_changed.connect(self.status_changed.emit)
        worker.spam_detected.connect(self.spam_detected.emit)
        worker.message_reaction_received.connect(self.message_reaction_received.emit)

        self.workers[bot_id] = worker
        worker.start()

    def stop_bot(self, bot_id: int):
        if bot_id in self.workers:
            w = self.workers[bot_id]
            w.stop()
            w.wait(2000)
            del self.workers[bot_id]

    def stop_all(self):
        for bot_id in list(self.workers.keys()):
            self.stop_bot(bot_id)

    def get_worker(self, bot_id: int) -> BotWorker:
        return self.workers.get(bot_id)

    def send_reaction(self, bot_id: int, chat_id: int, message_id: int, emoji: str):
        w = self.get_worker(bot_id)
        if w:
            w.send_reaction_async(chat_id, message_id, emoji)

    def send_chat_action(self, bot_id: int, chat_id: int, action: str = "typing"):
        w = self.get_worker(bot_id)
        if w:
            w.send_chat_action_async(chat_id, action)
