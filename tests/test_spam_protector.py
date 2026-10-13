import time
import pytest
from spam_protector import SpamProtector


class TestSpamProtector:
    def test_disabled_protector_allows_all(self):
        sp = SpamProtector(max_messages=3, window_seconds=5.0, enabled=False)
        bot_id, chat_id = 1, 100
        for _ in range(10):
            is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text="spam")
            assert is_spam is False
            assert is_perm is False
            assert reason == ""

    def test_normal_traffic_allowed(self):
        sp = SpamProtector(max_messages=5, window_seconds=5.0, enabled=True)
        bot_id, chat_id = 1, 100
        for i in range(4):
            is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text=f"Message {i}")
            assert is_spam is False
            assert is_perm is False
            assert reason == ""

    def test_rapid_messages_cooldown_and_permanent_escalation(self, monkeypatch):
        current_time = 1000.0

        def mock_time():
            return current_time

        monkeypatch.setattr(time, "time", mock_time)

        sp = SpamProtector(max_messages=4, window_seconds=5.0, enabled=True)
        bot_id, chat_id = 1, 100

        # Send 4 messages - allowed
        for i in range(4):
            is_spam, is_perm, _ = sp.check_incoming(bot_id, chat_id, text=f"Msg {i}")
            assert is_spam is False

        # 5th message (exceeds max_messages=4) -> 1st violation (temporary cooldown)
        is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text="Msg 4")
        assert is_spam is True
        assert is_perm is False
        assert "Geçici 45 sn mola" in reason

        # Immediate next message while still in cooldown (remaining ~45s)
        is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text="Msg 5")
        assert is_spam is True
        assert is_perm is False
        assert "Kullanıcı geçici molada" in reason

        # Advance time by 46 seconds (cooldown expires)
        current_time += 46.0

        # Send message after cooldown - cooldown expired, starts clean window
        is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text="Msg after cooldown")
        assert is_spam is False

        # Send rapidly again to trigger 2nd violation
        for i in range(3):
            sp.check_incoming(bot_id, chat_id, text=f"Msg burst {i}")

        # This burst triggers 2nd violation -> escalates to permanent block!
        is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text="Msg burst 3")
        assert is_spam is True
        assert is_perm is True
        assert "kalıcı engellendi" in reason

    def test_media_group_album_awareness(self, monkeypatch):
        current_time = 1000.0

        def mock_time():
            return current_time

        monkeypatch.setattr(time, "time", mock_time)

        # max_media = 3, max_messages = 15
        sp = SpamProtector(max_messages=15, max_media=3, media_window_seconds=8.0, enabled=True)
        bot_id, chat_id = 1, 200

        # Send an album of 8 photos with the same media_group_id within 2 seconds
        album_id = "album_12345"
        for _ in range(8):
            current_time += 0.2
            is_spam, is_perm, reason = sp.check_incoming(
                bot_id, chat_id, is_media=True, media_group_id=album_id
            )
            assert is_spam is False, f"Album photo triggered spam unexpectedly: {reason}"

        # Now send separate non-album media files rapidly
        # media_q already has 1 entry from the album.
        # i=0 -> media_q has 2 (<= 3) -> allowed
        # i=1 -> media_q has 3 (<= 3) -> allowed
        # i=2 -> media_q has 4 (> 3)  -> triggers media violation!
        # i=3 -> in cooldown          -> blocked with cooldown message
        current_time += 0.1
        is_spam, _, _ = sp.check_incoming(bot_id, chat_id, is_media=True, media_group_id=None)
        assert is_spam is False

        current_time += 0.1
        is_spam, _, _ = sp.check_incoming(bot_id, chat_id, is_media=True, media_group_id=None)
        assert is_spam is False

        current_time += 0.1
        is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, is_media=True, media_group_id=None)
        assert is_spam is True
        assert is_perm is False
        assert "Hızlı dosya/medya gönderimi" in reason

        current_time += 0.1
        is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, is_media=True, media_group_id=None)
        assert is_spam is True
        assert "Kullanıcı geçici molada" in reason

    def test_repeated_identical_text(self, monkeypatch):
        current_time = 1000.0

        def mock_time():
            return current_time

        monkeypatch.setattr(time, "time", mock_time)

        sp = SpamProtector(max_messages=20, window_seconds=10.0, enabled=True)
        bot_id, chat_id = 1, 300

        # Send 4 identical texts - allowed
        for _ in range(4):
            current_time += 0.5
            is_spam, is_perm, _ = sp.check_incoming(bot_id, chat_id, text="Aynı Metin Mesajı")
            assert is_spam is False

        # 5th identical text within 8 seconds - triggers violation
        current_time += 0.5
        is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text="Aynı Metin Mesajı")
        assert is_spam is True
        assert "Aynı metin 5 kez tekrarlandı" in reason

    def test_reset_user(self):
        sp = SpamProtector(max_messages=2, window_seconds=5.0, enabled=True)
        bot_id, chat_id = 1, 400

        sp.check_incoming(bot_id, chat_id, text="1")
        sp.check_incoming(bot_id, chat_id, text="2")
        is_spam, _, _ = sp.check_incoming(bot_id, chat_id, text="3")
        assert is_spam is True

        # Reset user
        sp.reset_user(bot_id, chat_id)
        assert (bot_id, chat_id) not in sp.violation_count
        assert (bot_id, chat_id) not in sp.mute_until
        assert len(sp.message_history[(bot_id, chat_id)]) == 0

        # Now sending 1 message should be allowed without penalty
        is_spam, _, _ = sp.check_incoming(bot_id, chat_id, text="New message")
        assert is_spam is False

    def test_multiple_chat_isolation_and_short_text(self):
        sp = SpamProtector(max_messages=2, window_seconds=5.0, enabled=True)
        # Chat 1 sends 2 messages (at threshold)
        assert sp.check_incoming(1, 101, text="Hi")[0] is False
        assert sp.check_incoming(1, 101, text="Hi 2")[0] is False

        # Chat 2 sends messages - should not be affected by Chat 1
        assert sp.check_incoming(1, 102, text="From user 2")[0] is False
        assert sp.check_incoming(1, 102, text="From user 2 again")[0] is False

        # Short text repetitions (1 character like "." or "!") should not trigger repetition rule
        sp_rep = SpamProtector(max_messages=20, window_seconds=10.0, enabled=True)
        for _ in range(6):
            is_spam, _, _ = sp_rep.check_incoming(1, 103, text=".")
            assert is_spam is False
