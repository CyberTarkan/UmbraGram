import time
from collections import defaultdict, deque

class SpamProtector:
    """
    Smarter and more lenient anti-spam protector with:
    - Telegram media_group_id (album) recognition (prevents banning legitimate photo albums).
    - Higher thresholds (12 messages in 5s, 10 media in 8s).
    - Graduated penalty: 1st violation gives a 45-second temporary cooldown, only 2nd violation leads to permanent block.
    """
    def __init__(self, max_messages: int = 12, window_seconds: float = 5.0,
                 max_media: int = 10, media_window_seconds: float = 8.0, enabled: bool = True):
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self.max_media = max_media
        self.media_window_seconds = media_window_seconds
        self.enabled = enabled

        # Store recent event timestamps per (bot_id, chat_id)
        self.message_history = defaultdict(deque)
        self.media_history = defaultdict(deque)
        self.text_history = defaultdict(deque)
        self.last_media_group = {} # key: (group_id, timestamp)

        # Graduated penalties
        self.mute_until = {}      # key: timestamp until when user is muted
        self.violation_count = defaultdict(int)

    def check_incoming(self, bot_id: int, chat_id: int, is_media: bool = False,
                       media_group_id: str = None, text: str = "") -> tuple[bool, bool, str]:
        """
        Returns (is_spam: bool, is_permanent: bool, reason: str)
        """
        if not self.enabled:
            return False, False, ""

        now = time.time()
        key = (bot_id, chat_id)

        # 0. Check active temporary cooldown
        if key in self.mute_until:
            remaining = int(self.mute_until[key] - now)
            if remaining > 0:
                # Still in cooldown
                return True, False, f"Kullanıcı geçici molada ({remaining} sn kaldı)"
            else:
                # Cooldown expired
                del self.mute_until[key]

        # 1. Clean old message timestamps
        msg_q = self.message_history[key]
        while msg_q and now - msg_q[0] > self.window_seconds:
            msg_q.popleft()

        msg_q.append(now)
        if len(msg_q) > self.max_messages:
            return self._apply_violation(key, f"Hızlı mesaj gönderimi ({len(msg_q)} mesaj / {self.window_seconds} sn)")

        # 2. Check media spam (with Album / Media Group awareness)
        if is_media:
            # If part of an album already tracked within 4 seconds, don't double count
            is_new_album_or_item = True
            if media_group_id:
                last_grp, last_ts = self.last_media_group.get(key, (None, 0))
                if last_grp == media_group_id and (now - last_ts < 4.0):
                    is_new_album_or_item = False
                self.last_media_group[key] = (media_group_id, now)

            if is_new_album_or_item:
                media_q = self.media_history[key]
                while media_q and now - media_q[0] > self.media_window_seconds:
                    media_q.popleft()
                media_q.append(now)
                if len(media_q) > self.max_media:
                    return self._apply_violation(key, f"Hızlı dosya/medya gönderimi ({len(media_q)} dosya / {self.media_window_seconds} sn)")

        # 3. Identical repeated text check (e.g. 5 times identical text in 8 seconds)
        if text and len(text.strip()) > 1:
            txt_q = self.text_history[key]
            while txt_q and now - txt_q[0][0] > 8.0:
                txt_q.popleft()
            txt_q.append((now, text.strip()))
            same_count = sum(1 for _, t in txt_q if t == text.strip())
            if same_count >= 5:
                return self._apply_violation(key, f"Aynı metin 5 kez tekrarlandı")

        return False, False, ""

    def _apply_violation(self, key: tuple, reason: str) -> tuple[bool, bool, str]:
        now = time.time()
        self.violation_count[key] += 1
        count = self.violation_count[key]

        if count == 1:
            # 1st violation: 45-second temporary cooldown, not permanent ban
            self.mute_until[key] = now + 45.0
            return True, False, f"Geçici 45 sn mola uygulandı ({reason})"
        else:
            # 2nd or higher violation: escalate to permanent block
            return True, True, f"Tekrarlanan spam nedeniyle kalıcı engellendi ({reason})"

    def reset_user(self, bot_id: int, chat_id: int):
        key = (bot_id, chat_id)
        self.message_history.pop(key, None)
        self.media_history.pop(key, None)
        self.text_history.pop(key, None)
        self.last_media_group.pop(key, None)
        self.mute_until.pop(key, None)
        self.violation_count.pop(key, None)
