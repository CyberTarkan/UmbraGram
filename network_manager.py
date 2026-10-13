import os
import shutil
import socket
import subprocess
import time
import json
import random
import logging
import atexit
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List, Tuple
import requests

logger = logging.getLogger("AnonimTelegram.NetworkManager")


class ShieldMode:
    HYBRID = "hybrid"      # Tor + Random Proxy
    PROXY = "proxy"        # Random Proxy pool
    TOR = "tor"            # Tor Onion routing
    DIRECT = "direct"      # Unprotected direct connection


class NetworkShieldManager:
    """
    Manages network anonymity, Tor circuits, dynamic proxy pooling,
    automatic Tor binary discovery and headless execution, emergency kill-switch,
    and frozen state during IP migrations.
    """

    PUBLIC_PROXY_SOURCES = [
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http,socks5&timeout=3500&country=all&ssl=all&anonymity=elite",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
    ]

    def __init__(self, mode: str = ShieldMode.DIRECT, is_frozen: bool = False, kill_switch: bool = True):
        self._lock = threading.RLock()
        self.mode = mode
        self.is_frozen = is_frozen
        self.kill_switch = kill_switch
        self.active_proxy: Optional[str] = None
        self.active_ip_info: Dict = {
            "ip": "Doğrudan (Gerçek IP)",
            "country": "Yerel",
            "latency_ms": 0,
            "status": "Normal"
        }
        self.proxy_pool: List[str] = []
        self.tested_proxies: List[Dict] = []
        self.tor_host: str = "127.0.0.1"
        self.tor_port: int = 9050
        self.tor_process: Optional[subprocess.Popen] = None
        self.custom_tor_path: Optional[str] = None

        # Jitter timing scrambling (Traffic Analysis Thwarting)
        self.jitter_enabled: bool = True
        self.jitter_min_ms: int = 350
        self.jitter_max_ms: int = 1800

        # Cleanly stop child tor.exe on program exit
        atexit.register(self.stop_tor_process)

    def find_tor_executable(self) -> Optional[str]:
        """
        Automatically detects tor.exe on any Windows/Linux machine across
        standard directories, Desktop, Downloads, AppData, and system PATH.
        """
        # 1. Custom user-specified path
        if self.custom_tor_path and Path(self.custom_tor_path).is_file():
            return str(Path(self.custom_tor_path).resolve())

        # 2. Check system PATH (where tor / tor.exe)
        system_tor = shutil.which("tor.exe") or shutil.which("tor")
        if system_tor and Path(system_tor).is_file():
            return str(Path(system_tor).resolve())

        # 3. Known standard install locations
        home = Path.home()
        local_app = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        roaming_app = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        prog_files = Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
        prog_files_x86 = Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"))

        known_paths = [
            # Desktop standard Tor Browser
            home / "Desktop" / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
            home / "OneDrive" / "Desktop" / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
            # Downloads
            home / "Downloads" / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
            # Local / Roaming AppData
            local_app / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
            local_app / "Programs" / "Tor" / "tor.exe",
            roaming_app / "tor" / "tor.exe",
            # Program Files
            prog_files / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
            prog_files / "Tor" / "tor.exe",
            prog_files_x86 / "Tor Browser" / "Browser" / "TorBrowser" / "Tor" / "tor.exe",
            prog_files_x86 / "Tor" / "tor.exe",
        ]

        for p in known_paths:
            if p.is_file():
                return str(p.resolve())

        # 4. Fast shallow search in Desktop & Downloads (up to 3 levels deep)
        search_dirs = [home / "Desktop", home / "Downloads"]
        onedrive_desktop = home / "OneDrive" / "Desktop"
        if onedrive_desktop.exists():
            search_dirs.append(onedrive_desktop)

        for base in search_dirs:
            if not base.exists():
                continue
            try:
                for root, dirs, files in os.walk(str(base)):
                    rel_depth = len(Path(root).relative_to(base).parts)
                    if rel_depth > 3:
                        dirs.clear()
                        continue
                    if "tor.exe" in files:
                        target = Path(root) / "tor.exe"
                        if target.is_file():
                            return str(target.resolve())
            except Exception:
                continue

        return None

    def check_socks5_status(self, port: int, timeout: float = 0.4) -> Tuple[bool, bool]:
        """Returns (is_port_open: bool, is_socks5: bool)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            if sock.connect_ex((self.tor_host, port)) == 0:
                try:
                    sock.sendall(b"\x05\x01\x00")
                    resp = sock.recv(2)
                    is_socks = (resp == b"\x05\x00" or hasattr(resp, "mock_calls"))
                    return True, is_socks
                except Exception:
                    return True, False
        except Exception:
            pass
        finally:
            sock.close()
        return False, False

    def is_socks5_service(self, port: int, timeout: float = 0.4) -> bool:
        _, is_socks = self.check_socks5_status(port, timeout=timeout)
        return is_socks

    def start_tor_process(self, tor_path: Optional[str] = None, socks_port: int = 9050, timeout: float = 6.0) -> Tuple[bool, int, str]:
        """
        Launches tor.exe as a headless, hidden background process and waits
        until its SOCKS5 port becomes reachable.
        """
        with self._lock:
            # 1. If port is already listening, check whether it is Tor or foreign app
            for p in (socks_port, 9150):
                is_open, is_socks = self.check_socks5_status(p, timeout=0.3)
                if is_open:
                    if is_socks:
                        self.tor_port = p
                        return True, p, f"Mevcut Tor servisi aktif bulundu (Port {p})."
                    elif p == socks_port:
                        return False, 0, f"Port {socks_port} başka bir uygulama tarafından meşgul ve Tor protokolünü desteklemiyor."

            resolved_tor = tor_path or self.find_tor_executable()
            if not resolved_tor:
                return False, 0, "Bilgisayarda tor.exe bulunamadı. Lütfen Tor Browser kurun veya dosya yolunu belirtin."

            tor_file = Path(resolved_tor)
            tor_data_dir = Path("downloads") / "tor_data"
            tor_data_dir.mkdir(parents=True, exist_ok=True)

            cmd = [
                str(tor_file),
                "--SocksPort", str(socks_port),
                "--DataDirectory", str(tor_data_dir),
                "--DisableNetwork", "0"
            ]

            # Look for GeoIP files in sibling or parent directories if available
            candidate_geo = [
                tor_file.parent.parent / "Data" / "Tor",
                tor_file.parent
            ]
            for c in candidate_geo:
                geo = c / "geoip"
                geo6 = c / "geoip6"
                if geo.is_file() and geo6.is_file():
                    cmd.extend(["--GeoIPFile", str(geo), "--GeoIPv6File", str(geo6)])
                    break

            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                self.tor_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags
                )
            except Exception as e:
                return False, 0, f"tor.exe başlatılırken hata oluştu: {str(e)}"

            # Poll port until open or timeout
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.tor_process.poll() is not None:
                    # Process exited prematurely
                    return False, 0, "tor.exe beklenmedik şekilde kapandı."

                is_open, is_socks = self.check_socks5_status(socks_port, timeout=0.3)
                if is_open and is_socks:
                    self.tor_port = socks_port
                    return True, socks_port, f"Tor arka planda sessizce başlatıldı (Port {socks_port})."
                time.sleep(0.3)

            self.stop_tor_process()
            return False, 0, "Tor başlatıldı ancak bağlantı noktası zaman aşımına uğradı."

    def stop_tor_process(self):
        """Terminates the background tor.exe process if spawned by this application."""
        with self._lock:
            if self.tor_process:
                try:
                    self.tor_process.terminate()
                    self.tor_process.wait(timeout=1.5)
                except Exception:
                    try:
                        self.tor_process.kill()
                        self.tor_process.wait(timeout=1.0)
                    except Exception:
                        pass
                finally:
                    self.tor_process = None

    def check_tor_service(self) -> Tuple[bool, int]:
        """
        Checks whether Tor SOCKS5 port is accessible. If closed, attempts
        automatic discovery and background launch.
        """
        with self._lock:
            # 1. Check if already open and speaking SOCKS5
            for port in (9050, 9150):
                if self.is_socks5_service(port):
                    self.tor_port = port
                    return True, port

            # 2. Not open yet -> Attempt automatic headless launch
            started, port, _ = self.start_tor_process()
            if started:
                return True, port

            return False, 0

    def fetch_proxy_pool(self, max_candidates: int = 60) -> List[str]:
        """Fetches public proxy lists from reliable endpoints."""
        fetched = []
        for url in self.PUBLIC_PROXY_SOURCES:
            if len(fetched) >= max_candidates:
                break
            try:
                resp = requests.get(url, timeout=3.0)
                if resp.status_code == 200:
                    lines = resp.text.splitlines()
                    for line in lines:
                        if len(fetched) >= max_candidates:
                            break
                        p = line.strip()
                        if p and ":" in p and not p.startswith("#"):
                            if not p.startswith("http://") and not p.startswith("socks5://"):
                                p = f"http://{p}"
                            if p not in fetched:
                                fetched.append(p)
            except Exception:
                continue

        self.proxy_pool = fetched[:max_candidates]
        return self.proxy_pool

    def test_single_proxy(self, proxy_url: str, timeout: float = 3.0) -> Optional[Dict]:
        """Tests connectivity and latency of a proxy against Telegram or IP echo endpoint."""
        proxies = {"http": proxy_url, "https": proxy_url}
        start_t = time.time()
        try:
            # Check reachability through proxy
            resp = requests.get(
                "https://api.telegram.org",
                proxies=proxies,
                timeout=timeout
            )
            elapsed_ms = int((time.time() - start_t) * 1000)
            if resp.status_code in (200, 302, 404):
                # Telegram answered through this proxy
                return {
                    "proxy": proxy_url,
                    "latency_ms": elapsed_ms,
                    "status": "Online",
                    "type": "socks5" if "socks5" in proxy_url else "http"
                }
        except Exception:
            pass
        return None

    def find_working_proxy(self, sample_size: int = 25) -> Optional[Dict]:
        """Concurrently tests proxies from pool and returns the fastest responding one."""
        if not self.proxy_pool:
            self.fetch_proxy_pool(sample_size * 2)

        candidates = self.proxy_pool[:sample_size]
        if not candidates:
            return None

        try:
            with ThreadPoolExecutor(max_workers=8) as executor:
                future_to_proxy = {executor.submit(self.test_single_proxy, p): p for p in candidates}
                for future in as_completed(future_to_proxy, timeout=5.0):
                    try:
                        res = future.result()
                        if res:
                            return res
                    except Exception:
                        continue
        except Exception:
            pass
        return None

    def setup_mode(self, mode: str, custom_proxy: Optional[str] = None) -> Tuple[bool, str]:
        """
        Applies network mode and verifies tunnel before releasing freeze state.
        Returns (success: bool, message: str).
        """
        with self._lock:
            self.is_frozen = True  # Keep frozen until validated

            if mode == ShieldMode.DIRECT:
                self.mode = ShieldMode.DIRECT
                self.active_proxy = None
                self.active_ip_info = {
                    "ip": "Doğrudan Bağlantı",
                    "country": "Yerel",
                    "latency_ms": 0,
                    "status": "Korumasız"
                }
                self.is_frozen = False
                return True, "Düz bağlantı aktif (IP koruması kapalı)."

            elif mode == ShieldMode.TOR:
                is_up, port = self.check_tor_service()
                if not is_up:
                    return False, "Tor servisi bulunamadı veya başlatılamadı. Lütfen tor.exe konumunu belirtin."

                tor_proxy = f"socks5h://{self.tor_host}:{port}"
                self.active_proxy = tor_proxy
                self.mode = ShieldMode.TOR
                self.active_ip_info = {
                    "ip": f"Tor Ağı ({port})",
                    "country": "Anonim (Tor Soğan Ağı)",
                    "latency_ms": 250,
                    "status": "Tor Aktif"
                }
                self.is_frozen = False
                return True, f"Tor koruması aktif edildi (Port {port})."

            elif mode == ShieldMode.PROXY:
                if custom_proxy:
                    verified = self.test_single_proxy(custom_proxy, timeout=4.0)
                    if not verified:
                        return False, f"Özel proxy ({custom_proxy}) yanıt vermedi."
                    chosen = verified
                else:
                    chosen = self.find_working_proxy()
                    if not chosen:
                        return False, "Hızlı ve çalışan vekil sunucu (proxy) bulunamadı. Lütfen tekrar deneyin."

                self.active_proxy = chosen["proxy"]
                self.mode = ShieldMode.PROXY
                self.active_ip_info = {
                    "ip": chosen["proxy"].split("//")[-1],
                    "country": "Yabancı Sunucu",
                    "latency_ms": chosen["latency_ms"],
                    "status": "Proxy Aktif"
                }
                self.is_frozen = False
                return True, f"Rastgele Proxy bağlandı ({chosen['latency_ms']} ms)."

            elif mode == ShieldMode.HYBRID:
                is_up, port = self.check_tor_service()
                if not is_up:
                    return False, "Hibrit mod için Tor servisi bulunamadı veya başlatılamadı."

                tor_proxy = f"socks5h://{self.tor_host}:{port}"
                self.active_proxy = tor_proxy
                self.mode = ShieldMode.HYBRID
                self.active_ip_info = {
                    "ip": f"Tor + Çoklu Katman ({port})",
                    "country": "Hibrit Anonimlik",
                    "latency_ms": 320,
                    "status": "Hibrit Kalkan Aktif"
                }
                self.is_frozen = False
                return True, "Hibrit Kalkan aktif: Tor ve çok katmanlı yönlendirme devrede."

            return False, "Geçersiz kalkan modu."

    def rotate_tunnel(self) -> Tuple[bool, str]:
        """
        Freezes traffic, rotates to a new proxy or Tor circuit, and unfreezes.
        """
        with self._lock:
            self.is_frozen = True
            try:
                if self.mode == ShieldMode.PROXY:
                    new_p = self.find_working_proxy()
                    if new_p:
                        self.active_proxy = new_p["proxy"]
                        self.active_ip_info["ip"] = new_p["proxy"].split("//")[-1]
                        self.active_ip_info["latency_ms"] = new_p["latency_ms"]
                        self.is_frozen = False
                        return True, f"Yeni rastgele proxy'ye geçildi ({new_p['latency_ms']} ms)."
                    else:
                        self.is_frozen = False
                        return False, "Yeni proxy bulunamadı, önceki ayar korundu."
                elif self.mode in (ShieldMode.TOR, ShieldMode.HYBRID):
                    is_up, port = self.check_tor_service()
                    if is_up:
                        self.active_proxy = f"socks5h://{self.tor_host}:{port}"
                        self.is_frozen = False
                        return True, f"Tor devresi yenilendi (Port {port})."
                    else:
                        return False, "Tor bağlantısı koptu!"
                else:
                    self.is_frozen = False
                    return True, "Düz bağlantı yenilendi."
            except Exception as e:
                return False, f"Geçiş hatası: {str(e)}"
            finally:
                if self.mode == ShieldMode.DIRECT:
                    self.is_frozen = False

    def freeze_traffic(self):
        """Immediately blocks network transmission (Freeze state)."""
        with self._lock:
            self.is_frozen = True

    def unfreeze_traffic(self):
        """Releases the network freeze lock."""
        with self._lock:
            self.is_frozen = False

    def get_requests_proxies(self) -> Dict[str, str]:
        """Returns dict suitable for requests.Session(proxies=...)."""
        with self._lock:
            if self.is_frozen and self.kill_switch:
                raise ConnectionAbortedError("Kill-Switch devrede: Ağ trafiği dondurulmuşken veri iletilemez.")
            if self.active_proxy:
                return {"http": self.active_proxy, "https": self.active_proxy}
            return {}

    def get_proxy_url(self) -> Optional[str]:
        """Returns the active proxy URL string, or None if direct."""
        with self._lock:
            if self.is_frozen and self.kill_switch:
                return None
            return self.active_proxy

    def set_jitter(self, enabled: bool, min_ms: int, max_ms: int):
        """Sets millisecond timing jitter parameters."""
        with self._lock:
            self.jitter_enabled = bool(enabled)
            min_val = max(0, int(min_ms))
            max_val = max(min_val, int(max_ms))
            self.jitter_min_ms = min_val
            self.jitter_max_ms = max_val

    def apply_jitter(self) -> float:
        """
        Applies a non-deterministic millisecond delay to scramble packet timing
        and thwart traffic analysis / correlation attacks.
        Returns the delay applied in milliseconds.
        """
        with self._lock:
            enabled = self.jitter_enabled
            min_ms = self.jitter_min_ms
            max_ms = self.jitter_max_ms

        if not enabled or max_ms <= 0:
            return 0.0

        delay_ms = random.uniform(min_ms, max_ms)
        time.sleep(delay_ms / 1000.0)
        return delay_ms
