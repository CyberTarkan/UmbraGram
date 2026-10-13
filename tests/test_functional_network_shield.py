import os
import time
import socket
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from network_manager import NetworkShieldManager, ShieldMode
from telegram_service import BotWorker, BotManager, SendActionWorker, FetchProfileWorker
from main import MainWindow, NetworkShieldStartupDialog, NetworkShieldSettingsDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ====================================================================
# 1. Tor Executable Detection Test (Live)
# ====================================================================
class TestTorExecutableDetectionLive:
    def test_find_tor_executable_live_system(self):
        mgr = NetworkShieldManager()
        detected_path = mgr.find_tor_executable()

        assert detected_path is not None, "tor.exe bu sistemde tespit edilemedi!"
        expected_substring = r"Desktop\Tor Browser\Browser\TorBrowser\Tor\tor.exe"
        assert expected_substring.lower() in detected_path.lower(), (
            f"Beklenen Tor konumu bulunamadı. Bulunan: {detected_path}"
        )
        assert os.path.isfile(detected_path), f"Bulunan dosya mevcut değil: {detected_path}"
        assert detected_path.lower().endswith("tor.exe"), "Dosya adı tor.exe olmalı."

    def test_find_tor_executable_custom_path_priority(self):
        mgr = NetworkShieldManager()
        mgr.custom_tor_path = r"C:\fake\custom\path\tor.exe"
        with patch("pathlib.Path.is_file", return_value=True):
            res = mgr.find_tor_executable()
            assert "custom" in res.lower()


# ====================================================================
# 2. Live Headless Tor Process Lifecycle Test (start_tor_process & stop)
# ====================================================================
class TestTorProcessLifecycleLive:
    def test_tor_start_connect_and_stop_live(self):
        mgr = NetworkShieldManager()
        tor_path = mgr.find_tor_executable()
        assert tor_path and os.path.isfile(tor_path), "tor.exe bulunamadığı için canlı süreç testi yapılamıyor."

        test_port = 9050

        # Ensure port is clean before test
        s = socket.socket()
        s.settimeout(0.3)
        initial_status = s.connect_ex(("127.0.0.1", test_port))
        s.close()

        # If already occupied by an existing process, test reuse or proceed
        if initial_status == 0:
            # Port already open (e.g. background service), test start_tor_process reuse
            started, port, msg = mgr.start_tor_process(tor_path=tor_path, socks_port=test_port)
            assert started is True
            assert port in (9050, 9150)
            assert "aktif bulundu" in msg
        else:
            # Clean start test
            started, port, msg = mgr.start_tor_process(tor_path=tor_path, socks_port=test_port, timeout=8.0)
            assert started is True, f"Tor başlatılamadı: {msg}"
            assert port == test_port
            assert mgr.tor_process is not None
            assert mgr.tor_process.poll() is None, "Tor süreci beklenmedik şekilde kapandı."

            # Verify TCP connect
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            connect_code = sock.connect_ex(("127.0.0.1", test_port))
            assert connect_code == 0, f"Port {test_port} soket bağlantısı kurulamadı."

            # Verify Tor SOCKS5 protocol handshake: send [0x05, 0x01 (1 method), 0x00 (no auth)]
            sock.sendall(b"\x05\x01\x00")
            socks_resp = sock.recv(2)
            sock.close()
            assert socks_resp == b"\x05\x00", f"Tor SOCKS5 el sıkışma yanıtı geçersiz: {socks_resp}"

            # Stop Tor cleanly
            mgr.stop_tor_process()
            assert mgr.tor_process is None, "tor_process referansı sıfırlanmadı."

            # Verify port is closed
            time.sleep(0.6)
            sock_after = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock_after.settimeout(0.5)
            after_code = sock_after.connect_ex(("127.0.0.1", test_port))
            sock_after.close()
            assert after_code != 0, f"Tor durdurulduktan sonra Port {test_port} hala açık!"


# ====================================================================
# 3. Proxy Pool Functions & Timeout Mechanism Tests
# ====================================================================
class TestProxyPoolMechanisms:
    def test_fetch_proxy_pool_live_or_mock(self):
        mgr = NetworkShieldManager()
        proxies = mgr.fetch_proxy_pool(max_candidates=15)
        # Should return a list
        assert isinstance(proxies, list)
        if proxies:
            assert len(proxies) <= 15
            for p in proxies:
                assert p.startswith("http://") or p.startswith("socks5://")
                assert ":" in p

    def test_single_proxy_timeout_enforced(self):
        mgr = NetworkShieldManager()
        # 192.0.2.1 is TEST-NET-1 (non-routable blackhole IP)
        t_start = time.time()
        res = mgr.test_single_proxy("http://192.0.2.1:8888", timeout=1.2)
        elapsed = time.time() - t_start

        assert res is None, "Blackhole IP yanıt vermemeli."
        # Verify timeout duration is strictly adhered to (within margin)
        assert 1.0 <= elapsed <= 3.0, f"Zaman aşımı süresi beklenenden saptı: {elapsed:.2f}s"

    def test_find_working_proxy_concurrency_and_detection(self):
        mgr = NetworkShieldManager()
        mgr.proxy_pool = ["http://10.0.0.1:8080", "socks5://10.0.0.2:1080"]

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        def mock_get(url, proxies=None, timeout=None):
            if proxies and "10.0.0.2" in str(proxies):
                return mock_resp
            raise requests.exceptions.ConnectTimeout("Bağlantı zaman aşımı")

        with patch("requests.get", side_effect=mock_get):
            working = mgr.find_working_proxy(sample_size=2)
            assert working is not None
            assert working["proxy"] == "socks5://10.0.0.2:1080"
            assert working["type"] == "socks5"
            assert working["status"] == "Online"


# ====================================================================
# 4. Emergency Kill-Switch & Zero-Leak Frozen State Tests
# ====================================================================
class TestZeroLeakKillSwitch:
    def test_send_action_worker_zero_packets_when_frozen(self):
        net_mgr = NetworkShieldManager(is_frozen=True, kill_switch=True)
        callback_mock = MagicMock()

        worker = SendActionWorker(
            token="123456:FAKE_TOKEN",
            action="sendMessage",
            params={"chat_id": 999, "text": "Gizli Mesaj"},
            callback=callback_mock,
            network_manager=net_mgr
        )

        with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
            worker.run()
            # Absolute Zero Packet Verification: neither post nor get should be called
            assert mock_post.call_count == 0, "Dondurulmuş ağda requests.post çağrıldı! IP Sızıntısı!"
            assert mock_get.call_count == 0, "Dondurulmuş ağda requests.get çağrıldı! IP Sızıntısı!"

        callback_mock.assert_called_once()
        success, result, err = callback_mock.call_args[0]
        assert success is False
        assert "Ağ donduruldu" in err

    def test_fetch_profile_worker_zero_packets_when_frozen(self):
        net_mgr = NetworkShieldManager(is_frozen=True, kill_switch=True)
        callback_mock = MagicMock()

        worker = FetchProfileWorker(
            token="123456:FAKE_TOKEN",
            bot_id=1,
            chat_id=999,
            callback=callback_mock,
            network_manager=net_mgr
        )

        with patch("requests.Session.get") as mock_get:
            worker.run()
            assert mock_get.call_count == 0, "Dondurulmuş ağda profil çekme isteği gönderildi! IP Sızıntısı!"
        assert callback_mock.call_count == 0

    def test_bot_worker_polling_blocked_while_frozen(self):
        net_mgr = NetworkShieldManager(is_frozen=True, kill_switch=True)
        worker = BotWorker(
            bot_id=1,
            token="123456:FAKE_TOKEN",
            network_manager=net_mgr
        )

        with patch("requests.Session.get") as mock_get:
            # Simulate worker run for a short duration while frozen
            worker.is_running = True

            # BotWorker waits in while loop while is_frozen
            # We mock msleep to stop the worker after 2 iterations
            sleep_count = 0
            def fake_msleep(ms):
                nonlocal sleep_count
                sleep_count += 1
                if sleep_count >= 2:
                    worker.is_running = False

            worker.msleep = fake_msleep
            worker.run()

            # Zero network packets should have been emitted
            assert mock_get.call_count == 0, "BotWorker donmuş durumdayken getMe veya getUpdates çağrısı yaptı!"

    def test_network_manager_kill_switch_aborts_proxy_access(self):
        net_mgr = NetworkShieldManager(is_frozen=True, kill_switch=True)
        with pytest.raises(ConnectionAbortedError):
            net_mgr.get_requests_proxies()

        # url should return None when frozen with kill-switch
        assert net_mgr.get_proxy_url() is None

    def test_bot_manager_freeze_and_unfreeze_all_workers(self):
        net_mgr = NetworkShieldManager(is_frozen=False)
        bm = BotManager(network_manager=net_mgr)

        mock_worker = MagicMock()
        bm.workers[1] = mock_worker

        bm.freeze_all()
        assert net_mgr.is_frozen is True

        bm.unfreeze_all("http://5.5.5.5:8080")
        assert net_mgr.is_frozen is False
        mock_worker.update_proxy.assert_called_with("http://5.5.5.5:8080")


# ====================================================================
# 5. Offscreen PyQt6 UI Tests (Dialogs, Banners, Mode Switching)
# ====================================================================
class TestShieldUIOffscreen:
    def test_startup_dialog_mode_selection_and_lock(self, qapp):
        net_mgr = NetworkShieldManager(is_frozen=True)
        dlg = NetworkShieldStartupDialog(net_mgr)

        # Initial UI state
        assert dlg.rb_hybrid.isChecked() is True
        assert dlg.cb_kill_switch.isChecked() is True

        # Mode switch to Proxy
        dlg.rb_proxy.setChecked(True)
        with patch.object(net_mgr, "find_working_proxy", return_value={"proxy": "http://1.2.3.4:8080", "latency_ms": 150}):
            dlg._try_connect()
            assert net_mgr.mode == ShieldMode.PROXY
            assert net_mgr.active_proxy == "http://1.2.3.4:8080"
            assert net_mgr.is_frozen is False

    def test_startup_dialog_failure_keeps_button_active(self, qapp):
        net_mgr = NetworkShieldManager(is_frozen=True)
        dlg = NetworkShieldStartupDialog(net_mgr)
        dlg.rb_proxy.setChecked(True)

        with patch.object(net_mgr, "find_working_proxy", return_value=None):
            dlg._try_connect()
            # Connection failed, button should be re-enabled and error shown
            assert dlg.btn_connect.isEnabled() is True
            assert "❌" in dlg.status_lbl.text()
            assert net_mgr.is_frozen is True

    def test_main_window_freeze_banner_and_controls(self, qapp):
        with patch.object(BotManager, "start_bot"):
            net_mgr = NetworkShieldManager(mode=ShieldMode.TOR, is_frozen=False)
            win = MainWindow(net_manager=net_mgr)
            win.show()

            # Verify Tor shield button style
            assert "Tor" in win.btn_network_shield.text()

            # Freeze network
            win.set_network_frozen_ui(True, "Tor devresi yenileniyor...")
            assert win.network_freeze_banner.isVisible() is True
            assert "Tor devresi yenileniyor..." in win.network_freeze_banner_label.text()
            assert win.msg_input.isEnabled() is False
            assert win.btn_send.isEnabled() is False
            assert "donduruldu" in win.msg_input.placeholderText()

            # Unfreeze network
            win.set_network_frozen_ui(False)
            assert win.network_freeze_banner.isVisible() is False
            assert win.msg_input.isEnabled() is True
            assert win.btn_send.isEnabled() is True
            win.close()

    def test_settings_dialog_rotation_and_mode_switch(self, qapp):
        with patch.object(BotManager, "start_bot"):
            net_mgr = NetworkShieldManager(mode=ShieldMode.PROXY, is_frozen=False)
            win = MainWindow(net_manager=net_mgr)
            dlg = NetworkShieldSettingsDialog(net_mgr, win.bot_manager, win)

            assert "Proxy" in dlg.lbl_mode.text()

            # Test Proxy Rotation
            with patch.object(net_mgr, "find_working_proxy", return_value={"proxy": "http://7.7.7.7:8080", "latency_ms": 120}):
                dlg._rotate_proxy()
                assert net_mgr.active_proxy == "http://7.7.7.7:8080"
                assert "✅" in dlg.op_status_lbl.text()
                assert win.network_freeze_banner.isVisible() is False

            # Test Switch to Direct Mode
            dlg._switch_mode(ShieldMode.DIRECT)
            assert net_mgr.mode == ShieldMode.DIRECT
            assert "Düz Bağlantı" in dlg.lbl_mode.text()
            assert "Düz Bağlantı" in win.btn_network_shield.text()
            assert win.network_freeze_banner.isVisible() is False

            win.close()
