import os
import time
import socket
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from network_manager import NetworkShieldManager, ShieldMode
from telegram_service import BotWorker, BotManager, SendActionWorker, strip_media_metadata
from db_manager import DatabaseSecurityManager, DatabaseManager
from main import sanitize_url, safe_open_url, MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ====================================================================
# 1. Ağ Çökmesi & Beklenmedik Tor Kapanması (Crash & Recovery)
# ====================================================================
class TestCrashAndRecovery:
    def test_tor_abrupt_kill_and_immediate_recovery_live(self):
        mgr = NetworkShieldManager()
        tor_path = mgr.find_tor_executable()
        assert tor_path and os.path.isfile(tor_path), "tor.exe bulunamadı"

        # 1. Start Tor
        started, port, msg = mgr.start_tor_process(tor_path=tor_path, socks_port=9050, timeout=10.0)
        assert started is True, f"Tor başlatılamadı: {msg}"
        assert mgr.tor_process is not None
        assert mgr.tor_process.poll() is None

        # 2. Kill abruptly (SIGKILL simulation)
        mgr.tor_process.kill()
        mgr.tor_process.wait()
        time.sleep(0.3)
        assert mgr.tor_process.poll() is not None, "Süreç öldürülemedi"

        # Verify port is closed
        s = socket.socket()
        s.settimeout(0.3)
        assert s.connect_ex(("127.0.0.1", port)) != 0, "Öldürülen Tor'un portu hala açık!"
        s.close()

        # 3. Simulate recovery through check_tor_service
        is_up, new_port = mgr.check_tor_service()
        assert is_up is True, "Tor çökme sonrasında otomatik ayağa kaldırılamadı!"
        assert new_port == port

        # Clean shutdown
        mgr.stop_tor_process()
        assert mgr.tor_process is None

    def test_kill_switch_blocks_when_tor_crashes_mid_stream(self):
        mgr = NetworkShieldManager(mode=ShieldMode.TOR, is_frozen=False, kill_switch=True)
        mgr.active_proxy = "socks5h://127.0.0.1:9050"

        # Suddenly freeze network due to detected disconnect
        mgr.freeze_traffic()
        assert mgr.is_frozen is True

        # When frozen, get_requests_proxies must abort
        with pytest.raises(ConnectionAbortedError):
            mgr.get_requests_proxies()

        # Worker must zero-packet abort
        dispatched = []
        def dummy_cb(success, res, err):
            dispatched.append((success, err))

        worker = SendActionWorker(
            token="123:FAKE",
            action="sendMessage",
            params={"chat_id": 1, "text": "secret"},
            callback=dummy_cb,
            network_manager=mgr
        )
        with patch("requests.post") as mock_post:
            worker.run()
            assert mock_post.call_count == 0, "Tor çöktüğünde dondurulan ağda paket gönderildi!"

        assert len(dispatched) == 1
        assert dispatched[0][0] is False


# ====================================================================
# 2. Eşzamanlılık & Hızlı Rotasyon Stresi (Race Condition & Concurrency)
# ====================================================================
class TestConcurrencyAndBurstRotation:
    def test_rapid_burst_mode_switching(self):
        mgr = NetworkShieldManager(mode=ShieldMode.DIRECT)

        # Mock proxy finding to be fast
        with patch.object(mgr, "find_working_proxy", return_value={"proxy": "http://1.1.1.1:8080", "latency_ms": 50}):
            with patch.object(mgr, "check_tor_service", return_value=(True, 9050)):
                modes = [ShieldMode.DIRECT, ShieldMode.PROXY, ShieldMode.TOR, ShieldMode.HYBRID]
                for i in range(20):
                    m = modes[i % len(modes)]
                    success, msg = mgr.setup_mode(m)
                    assert success is True
                    assert mgr.mode == m
                    assert mgr.is_frozen is False

    def test_concurrent_traffic_during_rapid_rotations(self):
        """Simulates 10 concurrent threads trying to send messages while 5 threads rotate tunnels."""
        mgr = NetworkShieldManager(mode=ShieldMode.PROXY, kill_switch=True)
        mgr.active_proxy = "http://initial.proxy:8080"

        intercepted_calls = []
        errors = []

        def fake_post(url, **kwargs):
            proxies = kwargs.get("proxies", {})
            # Verify NO packet is ever sent with empty proxies (Direct) while in proxy mode
            if not proxies:
                errors.append("Unprotected packet detected! Proxies empty!")
            intercepted_calls.append(proxies)
            mock_r = MagicMock()
            mock_r.json.return_value = {"ok": True, "result": {"message_id": 100}}
            return mock_r

        stop_event = threading.Event()

        def rotator_worker():
            with patch.object(mgr, "find_working_proxy", return_value={"proxy": "http://rotated.proxy:8080", "latency_ms": 60}):
                while not stop_event.is_set():
                    mgr.freeze_traffic()
                    time.sleep(0.005)
                    mgr.rotate_tunnel()
                    time.sleep(0.005)

        def sender_worker():
            while not stop_event.is_set():
                w = SendActionWorker(
                    token="123:TOKEN",
                    action="sendMessage",
                    params={"chat_id": 1, "text": "concurrent test"},
                    network_manager=mgr
                )
                w.run()
                time.sleep(0.002)

        with patch("requests.post", side_effect=fake_post):
            rotator_threads = [threading.Thread(target=rotator_worker) for _ in range(4)]
            sender_threads = [threading.Thread(target=sender_worker) for _ in range(8)]

            for t in rotator_threads + sender_threads:
                t.daemon = True
                t.start()

            time.sleep(0.5)
            stop_event.set()

            for t in rotator_threads + sender_threads:
                t.join(timeout=1.0)

        assert len(errors) == 0, f"IP sızıntısı yakalandı: {errors}"
        mgr.unfreeze_traffic()


# ====================================================================
# 3. Bozuk Dosya & Uç Veri Girdileri (Corrupt Media & Extreme Inputs)
# ====================================================================
class TestCorruptedFilesAndExtremeInputs:
    def test_strip_metadata_empty_and_corrupt_files(self, tmp_path):
        # 1. Zero-byte files
        for ext in (".jpg", ".png", ".pdf", ".mp3", ".webp"):
            empty_file = tmp_path / f"empty{ext}"
            empty_file.write_bytes(b"")
            res = strip_media_metadata(str(empty_file))
            # Must not crash, should safely return original path or clean path
            assert os.path.exists(res)

        # 2. Corrupt / truncated files
        for ext in (".jpg", ".png", ".pdf", ".mp3"):
            garbage_file = tmp_path / f"corrupt{ext}"
            garbage_file.write_bytes(b"GARBAGE_RANDOM_CORRUPT_BYTES_XYZ_1234567890\x00\xff\xfe")
            res = strip_media_metadata(str(garbage_file))
            assert os.path.exists(res)

        # 3. Non-existent file
        res_non = strip_media_metadata(str(tmp_path / "does_not_exist.jpg"))
        assert res_non == str(tmp_path / "does_not_exist.jpg")

    def test_sanitize_url_extreme_inputs(self):
        # 1. 1000+ tracking query parameters
        huge_params = "&".join(f"utm_{i}=val_{i}&fbclid=evil_{i}&clean_{i}=ok_{i}" for i in range(500))
        huge_url = f"https://example.com/search?{huge_params}"
        cleaned = sanitize_url(huge_url)
        assert "clean_0=ok_0" in cleaned
        assert "fbclid=" not in cleaned

        # 2. Non-HTTP / Dangerous URI schemes
        assert sanitize_url("javascript:alert(document.cookie)") == "javascript:alert(document.cookie)"
        assert sanitize_url("data:text/html,<script>evil()</script>") == "data:text/html,<script>evil()</script>"
        assert sanitize_url("file:///C:/Windows/System32/cmd.exe") == "file:///C:/Windows/System32/cmd.exe"

        # 3. Non-string inputs
        assert sanitize_url(None) == ""
        assert sanitize_url(12345) == ""
        assert sanitize_url([]) == ""

        # 4. Extremely long string (100k characters)
        long_url = "https://example.com/" + ("a" * 100000)
        assert len(sanitize_url(long_url)) >= 100000

    def test_safe_open_url_blocks_dangerous_schemes(self):
        with patch("PyQt6.QtGui.QDesktopServices.openUrl") as mock_open:
            # Dangerous schemes should be rejected before opening
            safe_open_url("javascript:alert(1)")
            safe_open_url("file:///C:/Windows/cmd.exe")
            safe_open_url("data:text/html;base64,PHNjcmlwdD4=")
            assert mock_open.call_count == 0

    def test_database_security_extreme_passwords(self, tmp_path):
        vault_file = tmp_path / "test.vault"
        db_file = tmp_path / "test.db"
        db_file.write_bytes(b"SQLITE_DUMMY_DATABASE_CONTENT")

        sec = DatabaseSecurityManager(vault_path=str(vault_file), db_path=str(db_file))

        # 1. Extremely long password (2000 chars)
        long_pw = "P@ssw0rd_" + ("A" * 2000) + "_#999"
        sec.setup_master_password(long_pw)
        assert sec.is_vault_initialized() is True
        assert sec.verify_password(long_pw) is True
        assert sec.verify_password("wrong") is False

        # 2. Unicode, Emojis, RTL characters, Null bytes
        unicode_pw = "🔐🔒Türkiye_İstanbul_مرحبا_日本語_🔥\u202e\u200bSpecial"
        sec2 = DatabaseSecurityManager(vault_path=str(vault_file), db_path=str(db_file))
        sec2.setup_master_password(unicode_pw)
        assert sec2.verify_password(unicode_pw) is True
        assert sec2.verify_password(unicode_pw + "extra") is False


# ====================================================================
# 4. Zombi Süreç & Port Çakışması Denetimi
# ====================================================================
class TestZombieProcessAndPortConflicts:
    def test_repeated_tor_lifecycle_leaves_no_zombies_live(self):
        mgr = NetworkShieldManager()
        tor_path = mgr.find_tor_executable()
        assert tor_path and os.path.isfile(tor_path)

        pids = []
        for i in range(3):
            ok, port, msg = mgr.start_tor_process(tor_path=tor_path, socks_port=9050, timeout=10.0)
            assert ok is True
            pid = mgr.tor_process.pid
            pids.append(pid)
            mgr.stop_tor_process()
            assert mgr.tor_process is None
            time.sleep(0.4)

        # Verify none of the spawned PIDs are still running or listening on port 9050
        s = socket.socket()
        s.settimeout(0.3)
        res = s.connect_ex(("127.0.0.1", 9050))
        s.close()
        assert res != 0, "Port 9050 döngü sonrasında hala açık kaldı!"

    def test_foreign_application_port_9050_conflict(self):
        """Simulates another non-Tor application binding port 9050."""
        foreign_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        foreign_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            foreign_sock.bind(("127.0.0.1", 9050))
            foreign_sock.listen(5)
        except OSError:
            pytest.skip("Port 9050 zaten başka bir servis tarafından kullanılıyor.")

        try:
            mgr = NetworkShieldManager()
            # 1. is_socks5_service must return False for foreign server
            assert mgr.is_socks5_service(9050) is False

            # 2. check_socks5_status should detect port is open, but NOT socks5
            is_open, is_socks = mgr.check_socks5_status(9050)
            assert is_open is True
            assert is_socks is False

            # 3. start_tor_process must recognize port conflict without crashing
            ok, port, msg = mgr.start_tor_process(socks_port=9050)
            assert ok is False
            assert "başka bir uygulama tarafından meşgul" in msg
        finally:
            foreign_sock.close()
