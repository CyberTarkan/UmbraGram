import os
import pytest
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication, QDialog
from network_manager import NetworkShieldManager, ShieldMode
from telegram_service import BotWorker, BotManager, SendActionWorker
from main import MainWindow, NetworkShieldStartupDialog, NetworkShieldSettingsDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestNetworkShieldManager:
    def test_direct_mode_setup(self):
        mgr = NetworkShieldManager(is_frozen=True)
        assert mgr.is_frozen is True
        success, msg = mgr.setup_mode(ShieldMode.DIRECT)
        assert success is True
        assert mgr.mode == ShieldMode.DIRECT
        assert mgr.active_proxy is None
        assert mgr.is_frozen is False

    def test_kill_switch_blocks_when_frozen(self):
        mgr = NetworkShieldManager(is_frozen=True, kill_switch=True)
        mgr.active_proxy = "http://1.2.3.4:8080"
        with pytest.raises(ConnectionAbortedError):
            mgr.get_requests_proxies()

        mgr.unfreeze_traffic()
        proxies = mgr.get_requests_proxies()
        assert proxies == {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"}

    def test_tor_service_check_mock(self):
        mgr = NetworkShieldManager()
        with patch.object(mgr, "check_tor_service", return_value=(True, 9050)):
            success, msg = mgr.setup_mode(ShieldMode.TOR)
            assert success is True
            assert mgr.active_proxy == "socks5h://127.0.0.1:9050"
            assert mgr.is_frozen is False

        with patch.object(mgr, "check_tor_service", return_value=(False, 0)):
            success, msg = mgr.setup_mode(ShieldMode.TOR)
            assert success is False
            assert "Tor servisi" in msg

    def test_find_tor_executable(self):
        mgr = NetworkShieldManager()
        # Custom path priority
        mgr.custom_tor_path = "C:/fake/custom/tor.exe"
        with patch("pathlib.Path.is_file", return_value=True):
            found = mgr.find_tor_executable()
            assert "tor.exe" in found.lower()

        # Auto detection
        mgr.custom_tor_path = None
        detected = mgr.find_tor_executable()
        # If tor.exe exists on Desktop (like on this system), it should find it
        if detected:
            assert "tor.exe" in detected.lower()

    def test_start_and_stop_tor_process(self):
        mgr = NetworkShieldManager()
        # Mock process
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        with patch("subprocess.Popen", return_value=mock_proc):
            with patch("socket.socket") as mock_sock_cls:
                mock_sock = MagicMock()
                # 9050 closed, 9150 closed, then after spawn 9050 open
                mock_sock.connect_ex.side_effect = [1, 1, 0]
                mock_sock_cls.return_value = mock_sock
                started, port, msg = mgr.start_tor_process(tor_path="C:/fake/tor.exe", socks_port=9050)
                assert started is True
                assert port == 9050
                assert mgr.tor_process is not None

        # Stop process
        mgr.stop_tor_process()
        assert mgr.tor_process is None

    def test_proxy_mode_with_custom_proxy(self):
        mgr = NetworkShieldManager()
        with patch.object(mgr, "test_single_proxy", return_value={"proxy": "http://5.6.7.8:8080", "latency_ms": 110, "status": "Online"}):
            success, msg = mgr.setup_mode(ShieldMode.PROXY, custom_proxy="http://5.6.7.8:8080")
            assert success is True
            assert mgr.active_proxy == "http://5.6.7.8:8080"
            assert mgr.is_frozen is False

    def test_hybrid_mode_with_tor(self):
        mgr = NetworkShieldManager()
        with patch.object(mgr, "check_tor_service", return_value=(True, 9150)):
            success, msg = mgr.setup_mode(ShieldMode.HYBRID)
            assert success is True
            assert mgr.active_proxy == "socks5h://127.0.0.1:9150"
            assert mgr.mode == ShieldMode.HYBRID
            assert mgr.is_frozen is False

    def test_rotate_tunnel_freezes_and_unfreezes(self):
        mgr = NetworkShieldManager(mode=ShieldMode.PROXY)
        mgr.proxy_pool = ["http://10.0.0.1:8080"]
        with patch.object(mgr, "find_working_proxy", return_value={"proxy": "http://10.0.0.1:8080", "latency_ms": 95}):
            success, msg = mgr.rotate_tunnel()
            assert success is True
            assert mgr.active_proxy == "http://10.0.0.1:8080"
            assert mgr.is_frozen is False


class TestTelegramServiceShieldIntegration:
    def test_send_action_aborts_when_frozen(self):
        net_mgr = NetworkShieldManager(is_frozen=True)
        cb_called = []

        def callback(success, result, err):
            cb_called.append((success, err))

        worker = SendActionWorker(
            token="123:ABC",
            action="sendMessage",
            params={"chat_id": 1, "text": "test"},
            callback=callback,
            network_manager=net_mgr
        )
        worker.run()

        assert len(cb_called) == 1
        assert cb_called[0][0] is False
        assert "Ağ donduruldu" in cb_called[0][1]

    def test_bot_manager_freeze_and_unfreeze_all(self):
        net_mgr = NetworkShieldManager(is_frozen=False)
        bm = BotManager(network_manager=net_mgr)
        bm.freeze_all()
        assert net_mgr.is_frozen is True

        bm.unfreeze_all("http://9.9.9.9:8080")
        assert net_mgr.is_frozen is False


class TestShieldUIIntegration:
    def test_network_shield_startup_dialog(self, qapp):
        net_mgr = NetworkShieldManager(is_frozen=True)
        dlg = NetworkShieldStartupDialog(net_mgr)
        assert dlg.rb_hybrid.isChecked() is True
        assert dlg.cb_kill_switch.isChecked() is True

        # Switch to Direct
        dlg.rb_direct.setChecked(True)
        dlg._try_connect()
        assert net_mgr.mode == ShieldMode.DIRECT
        assert net_mgr.is_frozen is False

    def test_main_window_freeze_ui_flow(self, qapp):
        with patch.object(BotManager, "start_bot"):
            net_mgr = NetworkShieldManager(mode=ShieldMode.HYBRID, is_frozen=False)
            win = MainWindow(net_manager=net_mgr)
            win.show()

            assert win.btn_network_shield is not None
            assert "Hibrit" in win.btn_network_shield.text()

            # Freeze network
            win.set_network_frozen_ui(True, "Yeni proxy tüneline geçiliyor...")
            assert not win.network_freeze_banner.isHidden()
            assert win.msg_input.isEnabled() is False
            assert win.btn_send.isEnabled() is False

            # Unfreeze network
            win.set_network_frozen_ui(False)
            assert win.network_freeze_banner.isHidden()
            assert win.msg_input.isEnabled() is True
            assert win.btn_send.isEnabled() is True
            win.close()

    def test_network_shield_settings_dialog(self, qapp):
        with patch.object(BotManager, "start_bot"):
            net_mgr = NetworkShieldManager(mode=ShieldMode.PROXY, is_frozen=False)
            win = MainWindow(net_manager=net_mgr)
            win.db.set_setting("jitter_enabled", "1")
            net_mgr.jitter_enabled = True
            dlg = NetworkShieldSettingsDialog(net_mgr, win.bot_manager, win)
            assert "Proxy" in dlg.lbl_mode.text()

            # Test Jitter UI controls and persistence
            dlg.cb_jitter.setChecked(True)
            assert dlg.cb_jitter.isChecked() is True
            dlg.spin_min_ms.setValue(400)
            dlg.spin_max_ms.setValue(1200)
            assert net_mgr.jitter_min_ms == 400
            assert net_mgr.jitter_max_ms == 1200
            assert win.db.get_setting("jitter_min_ms") == "400"
            assert win.db.get_setting("jitter_max_ms") == "1200"

            dlg.cb_jitter.setChecked(False)
            assert net_mgr.jitter_enabled is False
            assert win.db.get_setting("jitter_enabled") == "0"
            win.db.set_setting("jitter_enabled", "1")
            win.close()

    def test_jitter_execution_and_clamping(self):
        net_mgr = NetworkShieldManager()
        net_mgr.set_jitter(True, 250, 600)
        assert net_mgr.jitter_min_ms == 250
        assert net_mgr.jitter_max_ms == 600

        # Min > Max clamping test
        net_mgr.set_jitter(True, 800, 300)
        assert net_mgr.jitter_min_ms == 800
        assert net_mgr.jitter_max_ms == 800

        net_mgr.set_jitter(True, 100, 300)
        with patch("time.sleep") as mock_sleep:
            delay = net_mgr.apply_jitter()
            assert 100 <= delay <= 300
            mock_sleep.assert_called_once()
            slept_sec = mock_sleep.call_args[0][0]
            assert abs(slept_sec - (delay / 1000.0)) < 1e-6

        # When disabled, no delay
        net_mgr.set_jitter(False, 100, 300)
        with patch("time.sleep") as mock_sleep:
            delay = net_mgr.apply_jitter()
            assert delay == 0.0
            mock_sleep.assert_not_called()

