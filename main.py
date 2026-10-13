import sys
import os
import time
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QScrollArea, QFrame, QTextEdit, QSplitter, QMessageBox, QComboBox,
    QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMenu, QCheckBox, QInputDialog, QToolTip, QTabWidget, QGridLayout,
    QSizePolicy, QSlider, QRadioButton, QButtonGroup, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QUrl, QPoint, QPointF, QThreadPool, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import (
    QFont, QPixmap, QAction, QDesktopServices, QKeySequence, QColor, QShortcut,
    QPainter, QPainterPath, QFontMetrics, QPen
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from db_manager import DatabaseManager, DatabaseSecurityManager
from spam_protector import SpamProtector
from telegram_service import BotManager
from network_manager import NetworkShieldManager, ShieldMode
from shredder import execute_emergency_self_destruct

TEMP_DIR = Path("downloads") / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def make_circular_pixmap(pixmap: QPixmap, size: int) -> QPixmap:
    """Clips a QPixmap into a circular shape with antialiasing."""
    if pixmap.isNull():
        return pixmap
    target = QPixmap(size, size)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    scaled = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    offset_x = (size - scaled.width()) // 2
    offset_y = (size - scaled.height()) // 2
    painter.drawPixmap(offset_x, offset_y, scaled)
    painter.end()
    return target


def make_clickable(widget, callback):
    """Safely binds a mouse click handler returning None to avoid SIP bad catcher errors."""
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    def on_click(event):
        callback()
    widget.mousePressEvent = on_click


AVATAR_PALETTES = [
    "#5288c1",  # Telegram Classic Blue
    "#4fae60",  # Emerald Green
    "#e57b32",  # Warm Amber
    "#e25363",  # Crimson Red
    "#8e5bbf",  # Royal Violet
    "#3ea4ca",  # Cyan Blue
    "#d34b80",  # Soft Rose Pink
]


def get_avatar_color(seed: str) -> str:
    """Returns a deterministic Telegram pastel palette color for a user initial."""
    if not seed:
        return AVATAR_PALETTES[0]
    total = sum(ord(c) for c in str(seed))
    return AVATAR_PALETTES[total % len(AVATAR_PALETTES)]


def sanitize_url(raw_url: str) -> str:
    """Removes surveillance, marketing, and affiliate tracking parameters from URLs."""
    if not isinstance(raw_url, str):
        return ""
    TRACKING_PARAMS = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'utm_id',
        'fbclid', 'gclid', 'gclsrc', 'dclid', 'msclkid', 'twclid', 'igshid',
        'mc_eid', '_ga', '_gl', 'si', 'ref', 'ref_src', 'referrer'
    }
    try:
        parsed = urlparse(raw_url)
        qs = parse_qsl(parsed.query, keep_blank_values=True)
        filtered = [(k, v) for k, v in qs if k.lower() not in TRACKING_PARAMS]
        clean_query = urlencode(filtered)
        return urlunparse(parsed._replace(query=clean_query))
    except Exception:
        return raw_url


class SafeUrlDialog(QDialog):
    """Warning and tracker sanitizer dialog before launching external URLs in browser."""
    def __init__(self, raw_url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dış Bağlantı Güvenlik Uyarısı")
        self.setFixedSize(480, 260)
        self.raw_url = raw_url
        self.clean_url = sanitize_url(raw_url)
        self.trackers_removed = (self.raw_url != self.clean_url)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        header = QLabel("🛡️ Dış Bağlantıyı Açmak Üzeresiniz")
        header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        header.setStyleSheet("color: #ffffff;")
        layout.addWidget(header)

        info = QLabel(
            "Bu bağlantı varsayılan internet tarayıcınızda açılacaktır.\n"
            "Gerçek IP adresinizin karşı web sitesine sızmaması için "
            "VPN veya Tor Browser kullanmanız önerilir."
        )
        info.setFont(QFont("Segoe UI", 9))
        info.setStyleSheet("color: #9bb7d4;")
        info.setWordWrap(True)
        layout.addWidget(info)

        card = QFrame()
        card.setStyleSheet("background-color: #17212b; border: 1px solid #242f3d; border-radius: 8px; padding: 6px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(4)

        if self.trackers_removed:
            badge = QLabel("✅ Takipçi kodlar (utm_*, fbclid vb.) temizlendi:")
            badge.setStyleSheet("color: #4cd964; font-size: 10px; font-weight: bold;")
            card_layout.addWidget(badge)

        url_lbl = QLabel(self.clean_url)
        url_lbl.setFont(QFont("Segoe UI", 8))
        url_lbl.setStyleSheet("color: #649ad4;")
        url_lbl.setWordWrap(True)
        card_layout.addWidget(url_lbl)
        layout.addWidget(card)

        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("📋 Kopyala")
        btn_copy.setToolTip("Temizlenmiş bağlantıyı panoya kopyala")
        btn_copy.clicked.connect(self._copy_link)
        btn_layout.addWidget(btn_copy)

        btn_layout.addStretch()

        btn_cancel = QPushButton("İptal")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_open = QPushButton("Tarayıcıda Aç")
        btn_open.setStyleSheet("background-color: #5288c1; color: white; border-radius: 6px; padding: 6px 14px; font-weight: bold;")
        btn_open.clicked.connect(self.accept)
        btn_layout.addWidget(btn_open)

        layout.addLayout(btn_layout)

    def _copy_link(self):
        QApplication.clipboard().setText(self.clean_url)
        QMessageBox.information(self, "Kopyalandı", "Temizlenmiş bağlantı panoya kopyalandı.")


def safe_open_url(raw_url: str, parent=None):
    if not raw_url:
        return
    clean = sanitize_url(raw_url)
    try:
        from urllib.parse import urlparse
        parsed = urlparse(clean)
        if parsed.scheme.lower() not in ('http', 'https'):
            return
    except Exception:
        return
    dlg = SafeUrlDialog(raw_url, parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        QDesktopServices.openUrl(QUrl(dlg.clean_url))


class MasterPasswordSetupDialog(QDialog):
    """First-time master password setup dialog to encrypt the local database with AES-256."""
    def __init__(self, sec_mgr: DatabaseSecurityManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Anonim Telegram - Güvenlik Anahtarı Belirleme")
        self.setFixedSize(460, 320)
        self.sec_mgr = sec_mgr

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        header_lbl = QLabel("🔐 Veritabanı Şifreleme Anahtarı")
        header_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        header_lbl.setStyleSheet("color: #ffffff;")
        layout.addWidget(header_lbl)

        info_frame = QFrame()
        info_frame.setStyleSheet("""
            background-color: rgba(82, 136, 193, 0.12);
            border: 1px solid rgba(82, 136, 193, 0.32);
            border-radius: 8px;
            padding: 8px;
        """)
        info_layout = QVBoxLayout(info_frame)
        info_txt = QLabel(
            "Tüm sohbetleriniz, mesaj geçmişiniz ve bot token'larınız cihazınızda AES-256 ile şifrelenir.\n\n"
            "⚠️ ÖNEMLİ: Lütfen belirleyeceğiniz şifreyi güvenli bir yere kaydedin. "
            "Şifreyi unutursanız verileriniz kurtarılamaz!"
        )
        info_txt.setFont(QFont("Segoe UI", 9))
        info_txt.setStyleSheet("color: #d1dbe5;")
        info_txt.setWordWrap(True)
        info_layout.addWidget(info_txt)
        layout.addWidget(info_frame)

        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setPlaceholderText("Ana Şifre (en az 4 karakter)")
        layout.addWidget(self.pwd_input)

        self.pwd_confirm = QLineEdit()
        self.pwd_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_confirm.setPlaceholderText("Ana Şifre (Tekrar)")
        layout.addWidget(self.pwd_confirm)

        self.cb_confirm = QCheckBox("Şifremi güvenli bir yere kaydettiğimi onaylıyorum.")
        self.cb_confirm.setFont(QFont("Segoe UI", 9))
        self.cb_confirm.setStyleSheet("color: #f5b041;")
        layout.addWidget(self.cb_confirm)

        btn_layout = QHBoxLayout()
        btn_skip = QPushButton("Şifresiz Devam Et (Test)")
        btn_skip.setToolTip("Şifreleme yapmadan devam et")
        btn_skip.clicked.connect(self.reject)
        btn_layout.addWidget(btn_skip)

        btn_layout.addStretch()

        btn_save = QPushButton("🔒 Şifrele ve Başlat")
        btn_save.setStyleSheet("background-color: #5288c1; color: white; border-radius: 6px; padding: 6px 14px; font-weight: bold;")
        btn_save.clicked.connect(self._save_password)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def _save_password(self):
        p1 = self.pwd_input.text()
        p2 = self.pwd_confirm.text()
        if len(p1) < 4:
            QMessageBox.warning(self, "Geçersiz Şifre", "Şifre en az 4 karakter olmalıdır.")
            return
        if p1 != p2:
            QMessageBox.warning(self, "Uyuşmuyor", "Girdiğiniz iki şifre birbiriyle eşleşmiyor.")
            return
        if not self.cb_confirm.isChecked():
            QMessageBox.warning(self, "Onay Gerekli", "Lütfen şifrenizi kaydettiğinizi belirten onay kutusunu işaretleyin.")
            return

        self.sec_mgr.setup_master_password(p1)
        QMessageBox.information(self, "Başarılı", "Veritabanınız başarıyla şifrelendi. Programı her açtığınızda bu şifre istenecektir.")
        self.accept()


class MasterPasswordUnlockDialog(QDialog):
    """Unlock modal on startup if database vault is encrypted."""
    def __init__(self, sec_mgr: DatabaseSecurityManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Anonim Telegram - Kilitli Veritabanı")
        self.setFixedSize(380, 200)
        self.sec_mgr = sec_mgr

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        header_lbl = QLabel("🔒 Veritabanı Kilitli")
        header_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        header_lbl.setStyleSheet("color: #ffffff;")
        layout.addWidget(header_lbl)

        sub_lbl = QLabel("Devam etmek için ana güvenlik şifrenizi girin:")
        sub_lbl.setFont(QFont("Segoe UI", 9))
        sub_lbl.setStyleSheet("color: #9bb7d4;")
        layout.addWidget(sub_lbl)

        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setPlaceholderText("Ana Şifreniz...")
        self.pwd_input.returnPressed.connect(self._try_unlock)
        layout.addWidget(self.pwd_input)

        btn_layout = QHBoxLayout()
        btn_exit = QPushButton("Çıkış")
        btn_exit.clicked.connect(self.reject)
        btn_layout.addWidget(btn_exit)

        btn_layout.addStretch()

        btn_unlock = QPushButton("Kilidi Aç")
        btn_unlock.setStyleSheet("background-color: #5288c1; color: white; border-radius: 6px; padding: 6px 16px; font-weight: bold;")
        btn_unlock.clicked.connect(self._try_unlock)
        btn_layout.addWidget(btn_unlock)

        layout.addLayout(btn_layout)

    def _try_unlock(self):
        pwd = self.pwd_input.text()
        if self.sec_mgr.verify_password(pwd):
            self.sec_mgr.decrypt_database()
            self.accept()
        else:
            QMessageBox.critical(self, "Hata", "Hatalı şifre! Lütfen tekrar deneyin.")
            self.pwd_input.selectAll()


class NetworkShieldStartupDialog(QDialog):
    """
    Startup network anonymity shield selection dialog.
    Guarantees ZERO network communication takes place until the user picks
    their anonymity mode.
    """
    def __init__(self, net_mgr: NetworkShieldManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Anonim Telegram - Ağ Güvenlik Kalkanı")
        self.setFixedSize(540, 580)
        self.net_mgr = net_mgr
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QLabel("🛡️ Ağ Güvenlik Kalkanı ve IP Gizleme")
        header.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        header.setStyleSheet("color: #ffffff;")
        layout.addWidget(header)

        sub_info = QLabel(
            "Telegram'a bağlanmadan önce gerçek IP adresinizi gizlemek için koruma yöntemini seçin.\n"
            "⚠️ Kalkan devreye girene kadar hiçbir mesaj alınıp verilmez (Sıfır IP Sızıntısı Koruması)."
        )
        sub_info.setFont(QFont("Segoe UI", 9))
        sub_info.setStyleSheet("color: #9bb7d4;")
        sub_info.setWordWrap(True)
        layout.addWidget(sub_info)

        # Hayati Anonimlik Uyarısı (Bot Hesabı Uyarısı)
        warn_box = QFrame()
        warn_box.setStyleSheet("""
            background-color: rgba(245, 176, 65, 0.12);
            border: 1px solid rgba(245, 176, 65, 0.4);
            border-radius: 8px;
            padding: 8px;
        """)
        wb_layout = QVBoxLayout(warn_box)
        wb_lbl = QLabel(
            "⚠️ <b>Hayati Anonimlik Uyarısı:</b> Telegram botunuzu kesinlikle kendi kişisel telefon numaranıza bağlı "
            "hesabınızdan veya ev internetinizden oluşturmayın! Botu oluşturan hesap kimliğinizle eşleşirse "
            "tüm ağ ve tünel kalkanları geçersiz kalır. Anonim/sanal bir Telegram hesabı kullanın."
        )
        wb_lbl.setWordWrap(True)
        wb_lbl.setStyleSheet("color: #f5b041; font-size: 11px;")
        wb_layout.addWidget(wb_lbl)
        layout.addWidget(warn_box)

        # Options Container Frame
        options_frame = QFrame()
        options_frame.setStyleSheet("""
            QFrame {
                background-color: #17212b;
                border: 1px solid #242f3d;
                border-radius: 10px;
                padding: 6px;
            }
        """)
        options_layout = QVBoxLayout(options_frame)
        options_layout.setSpacing(8)

        self.btn_group = QButtonGroup(self)

        # 1. Hybrid (Tor + Proxy)
        self.rb_hybrid = QRadioButton("🟣 Tor + Rastgele Proxy (Hibrit - Maksimum Anonimlik)")
        self.rb_hybrid.setChecked(True)
        self.rb_hybrid.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.rb_hybrid.setStyleSheet("color: #cf9fff; padding: 2px;")
        desc_hybrid = QLabel("    Çift katman: Önce Tor şifreli ağı, ardından rastgele yabancı sunucu. IP asla görünmez.")
        desc_hybrid.setStyleSheet("color: #7f91a4; font-size: 11px;")
        self.btn_group.addButton(self.rb_hybrid, 1)
        options_layout.addWidget(self.rb_hybrid)
        options_layout.addWidget(desc_hybrid)

        # 2. Random Proxy
        self.rb_proxy = QRadioButton("🟡 Sadece Rastgele Proxy (Hızlı IP Maskeleme)")
        self.rb_proxy.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.rb_proxy.setStyleSheet("color: #f5b041; padding: 2px;")
        desc_proxy = QLabel("    İnternetten anlık çalışan vekil sunucu bulunur. Tor uygulaması gerekmez.")
        desc_proxy.setStyleSheet("color: #7f91a4; font-size: 11px;")
        self.btn_group.addButton(self.rb_proxy, 2)
        options_layout.addWidget(self.rb_proxy)
        options_layout.addWidget(desc_proxy)

        # 3. Tor Only
        self.rb_tor = QRadioButton("🧅 Sadece Tor Ağı (Soğan Şifreleme)")
        self.rb_tor.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.rb_tor.setStyleSheet("color: #3ea4ca; padding: 2px;")
        desc_tor = QLabel("    Doğrudan bilgisayarınızdaki Tor servisi (Port 9050/9150) üzerinden 3 katmanlı tünel.")
        desc_tor.setStyleSheet("color: #7f91a4; font-size: 11px;")
        self.btn_group.addButton(self.rb_tor, 3)
        options_layout.addWidget(self.rb_tor)
        options_layout.addWidget(desc_tor)

        # 4. Direct
        self.rb_direct = QRadioButton("⚪ Düz Bağlantı (Korumasız)")
        self.rb_direct.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.rb_direct.setStyleSheet("color: #d1dbe5; padding: 2px;")
        desc_direct = QLabel("    Gerçek ev internetinizle bağlanır (IP gizleme kapalı).")
        desc_direct.setStyleSheet("color: #7f91a4; font-size: 11px;")
        self.btn_group.addButton(self.rb_direct, 4)
        options_layout.addWidget(self.rb_direct)
        options_layout.addWidget(desc_direct)

        layout.addWidget(options_frame)

        # Custom Proxy option
        custom_layout = QHBoxLayout()
        self.cb_custom_proxy = QCheckBox("Özel Proxy Kullan:")
        self.cb_custom_proxy.setStyleSheet("color: #d1dbe5; font-size: 11px;")
        self.input_custom_proxy = QLineEdit()
        self.input_custom_proxy.setPlaceholderText("http://IP:Port veya socks5://IP:Port")
        self.input_custom_proxy.setEnabled(False)
        self.cb_custom_proxy.toggled.connect(self.input_custom_proxy.setEnabled)
        custom_layout.addWidget(self.cb_custom_proxy)
        custom_layout.addWidget(self.input_custom_proxy)
        layout.addLayout(custom_layout)

        # Tor executable auto-detection status bar
        tor_exe = self.net_mgr.find_tor_executable()
        tor_box = QHBoxLayout()
        if tor_exe:
            self.lbl_tor_detect = QLabel(f"🧅 Tor Tespit Edildi: {Path(tor_exe).name} (Arka planda otomatik başlatılır)")
            self.lbl_tor_detect.setStyleSheet("color: #4cd964; font-size: 11px;")
        else:
            self.lbl_tor_detect = QLabel("🧅 Tor otomatik bulunamadı (Tor Browser açıkken de bağlanabilirsiniz)")
            self.lbl_tor_detect.setStyleSheet("color: #7f91a4; font-size: 11px;")
        tor_box.addWidget(self.lbl_tor_detect, 1)

        self.btn_browse_tor = QPushButton("📁 Gözat...")
        self.btn_browse_tor.setToolTip("tor.exe dosyasını manuel seçin")
        self.btn_browse_tor.setFixedHeight(24)
        self.btn_browse_tor.setStyleSheet("background-color: #242f3d; color: #d1dbe5; border-radius: 4px; padding: 2px 8px; font-size: 10px;")
        self.btn_browse_tor.clicked.connect(self._browse_tor)
        tor_box.addWidget(self.btn_browse_tor)
        layout.addLayout(tor_box)

        # Kill Switch Checkbox
        self.cb_kill_switch = QCheckBox("⚡ Acil Durum Şalteri (Kill-Switch) Aktif (Kopma anında IP sızıntısını durdur)")
        self.cb_kill_switch.setChecked(True)
        self.cb_kill_switch.setStyleSheet("color: #4cd964; font-weight: 500; font-size: 11px;")
        layout.addWidget(self.cb_kill_switch)

        # Status / Feedback label
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #f5b041; font-weight: bold; font-size: 11px;")
        self.status_lbl.setWordWrap(True)
        layout.addWidget(self.status_lbl)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_exit = QPushButton("Çıkış")
        self.btn_exit.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_exit)

        btn_layout.addStretch()

        self.btn_connect = QPushButton("🛡️ Kalkanı Kur ve Bağlan")
        self.btn_connect.setStyleSheet("background-color: #5288c1; color: white; border-radius: 6px; padding: 7px 18px; font-weight: bold;")
        self.btn_connect.clicked.connect(self._try_connect)
        btn_layout.addWidget(self.btn_connect)

        layout.addLayout(btn_layout)

    def _browse_tor(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "tor.exe Seç", "", "Yürütülebilir Dosyalar (*tor.exe;*tor;*.*)")
        if fpath:
            self.net_mgr.custom_tor_path = fpath
            self.lbl_tor_detect.setText(f"🧅 Seçilen Tor: {Path(fpath).name}")
            self.lbl_tor_detect.setStyleSheet("color: #4cd964; font-size: 11px;")

    def _try_connect(self):
        if self.rb_hybrid.isChecked():
            mode = ShieldMode.HYBRID
        elif self.rb_proxy.isChecked():
            mode = ShieldMode.PROXY
        elif self.rb_tor.isChecked():
            mode = ShieldMode.TOR
        else:
            mode = ShieldMode.DIRECT

        custom = self.input_custom_proxy.text().strip() if self.cb_custom_proxy.isChecked() else None
        self.net_mgr.kill_switch = self.cb_kill_switch.isChecked()

        self.btn_connect.setEnabled(False)
        self.status_lbl.setText("⏳ Bağlantı tüneli test ediliyor ve kuruluyor...")
        QApplication.processEvents()

        success, msg = self.net_mgr.setup_mode(mode, custom_proxy=custom)
        if success:
            self.accept()
        else:
            self.status_lbl.setText(f"❌ {msg}")
            self.btn_connect.setEnabled(True)


class NetworkShieldSettingsDialog(QDialog):
    """
    In-app network shield and IP rotation panel.
    Allows rotating proxies or Tor circuits, changing modes, and tuning packet timing jitter.
    """
    def __init__(self, net_mgr: NetworkShieldManager, bot_manager, main_window, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ağ Güvenlik Kalkanı & IP Yönetimi")
        self.setFixedSize(500, 560)
        self.net_mgr = net_mgr
        self.bot_manager = bot_manager
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QLabel("🛡️ Canlı Ağ Kalkanı Durumu")
        header.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        header.setStyleSheet("color: #ffffff;")
        layout.addWidget(header)

        # Status Card
        self.card = QFrame()
        self.card.setStyleSheet("""
            QFrame {
                background-color: #17212b;
                border: 1px solid #242f3d;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setSpacing(6)

        self.lbl_mode = QLabel("")
        self.lbl_mode.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        card_layout.addWidget(self.lbl_mode)

        self.lbl_ip = QLabel("")
        self.lbl_ip.setStyleSheet("color: #d1dbe5; font-size: 12px;")
        card_layout.addWidget(self.lbl_ip)

        self.lbl_ping = QLabel("")
        self.lbl_ping.setStyleSheet("color: #7f91a4; font-size: 11px;")
        card_layout.addWidget(self.lbl_ping)

        layout.addWidget(self.card)
        self._update_card()

        # Rotation & Action Buttons
        actions_box = QFrame()
        actions_box.setStyleSheet("background-color: #17212b; border: 1px solid #242f3d; border-radius: 8px; padding: 8px;")
        actions_layout = QVBoxLayout(actions_box)
        actions_layout.setSpacing(8)

        lbl_acts = QLabel("Hızlı IP & Tünel Değiştirme:")
        lbl_acts.setStyleSheet("color: #9bb7d4; font-size: 11px; font-weight: bold;")
        actions_layout.addWidget(lbl_acts)

        btn_row1 = QHBoxLayout()
        self.btn_rotate_proxy = QPushButton("🔄 Yeni Rastgele Proxy Al")
        self.btn_rotate_proxy.setToolTip("İnternetten yeni çalışan yabancı IP sunucusuna geçiş yap")
        self.btn_rotate_proxy.setStyleSheet("background-color: #242f3d; color: #f5b041; border: 1px solid #f5b041; border-radius: 6px; padding: 6px; font-weight: bold;")
        self.btn_rotate_proxy.clicked.connect(self._rotate_proxy)
        btn_row1.addWidget(self.btn_rotate_proxy)

        self.btn_rotate_tor = QPushButton("🧅 Tor Devresini Yenile")
        self.btn_rotate_tor.setToolTip("Tor soğan tünel devresini yenileyip IP'yi tazele")
        self.btn_rotate_tor.setStyleSheet("background-color: #242f3d; color: #3ea4ca; border: 1px solid #3ea4ca; border-radius: 6px; padding: 6px; font-weight: bold;")
        self.btn_rotate_tor.clicked.connect(self._rotate_tor)
        btn_row1.addWidget(self.btn_rotate_tor)
        actions_layout.addLayout(btn_row1)

        # Mode quick switcher
        btn_row2 = QHBoxLayout()
        self.btn_to_hybrid = QPushButton("🟣 Hibrit Moda Geç")
        self.btn_to_hybrid.clicked.connect(lambda: self._switch_mode(ShieldMode.HYBRID))
        btn_row2.addWidget(self.btn_to_hybrid)

        self.btn_to_direct = QPushButton("⚪ Düz Bağlantıya Geç")
        self.btn_to_direct.clicked.connect(lambda: self._switch_mode(ShieldMode.DIRECT))
        btn_row2.addWidget(self.btn_to_direct)
        actions_layout.addLayout(btn_row2)

        layout.addWidget(actions_box)

        # Jitter Configuration Box
        jitter_box = QFrame()
        jitter_box.setStyleSheet("background-color: #17212b; border: 1px solid #242f3d; border-radius: 8px; padding: 8px;")
        jitter_layout = QVBoxLayout(jitter_box)
        jitter_layout.setSpacing(6)

        self.cb_jitter = QCheckBox("⏱️ Milisaniye Zaman İzi Karıştırıcısı (Jitter)")
        self.cb_jitter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.cb_jitter.setStyleSheet("color: #4cd964;")
        self.cb_jitter.setChecked(self.net_mgr.jitter_enabled)
        self.cb_jitter.setToolTip("Giden mesajlar arasına rastgele milisaniye gecikmesi ekleyerek Tor korelasyonunu ve trafik analizini engeller.")
        jitter_layout.addWidget(self.cb_jitter)

        jitter_desc = QLabel("Giden mesaj istekleri arasına rastgele milisaniye beklemesi ekleyerek paket zamanlamasından takip edilmeyi engeller.")
        jitter_desc.setStyleSheet("color: #7f91a4; font-size: 11px;")
        jitter_desc.setWordWrap(True)
        jitter_layout.addWidget(jitter_desc)

        spin_row = QHBoxLayout()
        spin_row.setSpacing(8)

        lbl_min = QLabel("Min Gecikme:")
        lbl_min.setStyleSheet("color: #d1dbe5; font-size: 11px;")
        spin_row.addWidget(lbl_min)

        self.spin_min_ms = QSpinBox()
        self.spin_min_ms.setRange(50, 10000)
        self.spin_min_ms.setSingleStep(50)
        self.spin_min_ms.setValue(self.net_mgr.jitter_min_ms)
        self.spin_min_ms.setSuffix(" ms")
        self.spin_min_ms.setStyleSheet("background-color: #242f3d; color: #ffffff; border-radius: 6px; padding: 3px 6px; font-size: 11px;")
        spin_row.addWidget(self.spin_min_ms)

        lbl_max = QLabel("Max Gecikme:")
        lbl_max.setStyleSheet("color: #d1dbe5; font-size: 11px;")
        spin_row.addWidget(lbl_max)

        self.spin_max_ms = QSpinBox()
        self.spin_max_ms.setRange(50, 10000)
        self.spin_max_ms.setSingleStep(50)
        self.spin_max_ms.setValue(self.net_mgr.jitter_max_ms)
        self.spin_max_ms.setSuffix(" ms")
        self.spin_max_ms.setStyleSheet("background-color: #242f3d; color: #ffffff; border-radius: 6px; padding: 3px 6px; font-size: 11px;")
        spin_row.addWidget(self.spin_max_ms)

        spin_row.addStretch()
        jitter_layout.addLayout(spin_row)

        self.cb_jitter.toggled.connect(self._save_jitter_settings)
        self.spin_min_ms.valueChanged.connect(self._on_min_spin_changed)
        self.spin_max_ms.valueChanged.connect(self._on_max_spin_changed)

        layout.addWidget(jitter_box)

        # Status text
        self.op_status_lbl = QLabel("")
        self.op_status_lbl.setStyleSheet("color: #f5b041; font-weight: bold; font-size: 11px;")
        self.op_status_lbl.setWordWrap(True)
        layout.addWidget(self.op_status_lbl)

        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _on_min_spin_changed(self, val):
        if val > self.spin_max_ms.value():
            self.spin_max_ms.setValue(val)
        self._save_jitter_settings()

    def _on_max_spin_changed(self, val):
        if val < self.spin_min_ms.value():
            self.spin_min_ms.setValue(val)
        self._save_jitter_settings()

    def _save_jitter_settings(self):
        enabled = self.cb_jitter.isChecked()
        min_ms = self.spin_min_ms.value()
        max_ms = self.spin_max_ms.value()
        self.net_mgr.set_jitter(enabled, min_ms, max_ms)
        if hasattr(self.main_window, 'db') and self.main_window.db:
            self.main_window.db.set_setting("jitter_enabled", "1" if enabled else "0")
            self.main_window.db.set_setting("jitter_min_ms", str(min_ms))
            self.main_window.db.set_setting("jitter_max_ms", str(max_ms))

    def _update_card(self):
        mode_titles = {
            ShieldMode.HYBRID: "🟣 Hibrit Kalkan (Tor + Rastgele Proxy)",
            ShieldMode.PROXY: "🟡 Rastgele Proxy Havuzu",
            ShieldMode.TOR: "🧅 Tor Soğan Ağı",
            ShieldMode.DIRECT: "⚪ Düz Bağlantı (Korumasız)"
        }
        self.lbl_mode.setText(mode_titles.get(self.net_mgr.mode, self.net_mgr.mode))
        info = self.net_mgr.active_ip_info
        self.lbl_ip.setText(f"Görünen IP: {info.get('ip', 'Bilinmiyor')} ({info.get('country', '')})")
        self.lbl_ping.setText(f"Tünel Gecikmesi: {info.get('latency_ms', 0)} ms | Durum: {info.get('status', 'Aktif')}")

    def _rotate_proxy(self):
        self.main_window.set_network_frozen_ui(True, "Yeni Proxy aranıyor... Mesaj trafiği donduruldu (IP sızıntı koruması aktif).")
        self.op_status_lbl.setText("⏳ Yeni proxy test ediliyor...")
        QApplication.processEvents()

        success, msg = self.net_mgr.rotate_tunnel()
        if success:
            new_p = self.net_mgr.get_proxy_url()
            self.bot_manager.unfreeze_all(new_p)
            self.main_window.set_network_frozen_ui(False)
            self._update_card()
            self.op_status_lbl.setText(f"✅ {msg}")
        else:
            self.main_window.set_network_frozen_ui(False)
            self.op_status_lbl.setText(f"❌ {msg}")

    def _rotate_tor(self):
        self.main_window.set_network_frozen_ui(True, "Tor devresi yenileniyor... Mesaj trafiği donduruldu.")
        self.op_status_lbl.setText("⏳ Tor devresi yenileniyor...")
        QApplication.processEvents()

        success, msg = self.net_mgr.setup_mode(ShieldMode.TOR)
        if success:
            new_p = self.net_mgr.get_proxy_url()
            self.bot_manager.unfreeze_all(new_p)
            self.main_window.set_network_frozen_ui(False)
            self._update_card()
            self.op_status_lbl.setText(f"✅ {msg}")
        else:
            self.main_window.set_network_frozen_ui(False)
            self.op_status_lbl.setText(f"❌ {msg}")

    def _switch_mode(self, new_mode: str):
        self.main_window.set_network_frozen_ui(True, f"{new_mode.upper()} moduna geçiliyor... Trafik donduruldu.")
        self.op_status_lbl.setText("⏳ Yeni tünel kuruluyor...")
        QApplication.processEvents()

        success, msg = self.net_mgr.setup_mode(new_mode)
        if success:
            new_p = self.net_mgr.get_proxy_url()
            self.bot_manager.unfreeze_all(new_p)
            self.main_window.set_network_frozen_ui(False)
            self._update_card()
            self.op_status_lbl.setText(f"✅ {msg}")
        else:
            self.main_window.set_network_frozen_ui(False)
            self.op_status_lbl.setText(f"❌ {msg}")


class TelegramDeleteDialog(QDialog):
    """Telegram-like delete confirmation modal with 'Delete for [User]' checkbox."""
    def __init__(self, target_user_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mesajı Sil")
        self.setFixedSize(360, 180)
        self.delete_for_everyone = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 15)
        layout.setSpacing(15)

        title_lbl = QLabel("Bu mesajı silmek istediğinize emin misiniz?")
        title_lbl.setFont(QFont("Segoe UI", 10))
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet("color: #ffffff;")
        layout.addWidget(title_lbl)

        display_name = (target_user_name[:24] + "...") if len(target_user_name) > 24 else target_user_name
        self.cb_everyone = QCheckBox(f"{display_name} için de sil (Herkesten sil)")
        self.cb_everyone.setChecked(True)
        self.cb_everyone.setFont(QFont("Segoe UI", 10))
        self.cb_everyone.setStyleSheet("color: #e4ecf2;")
        self.cb_everyone.setToolTip("İşaretlenirse mesaj hem sizden hem de karşı kullanıcının Telegram sohbetinden silinir")
        layout.addWidget(self.cb_everyone)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("İptal")
        btn_cancel.setToolTip("Silme işlemini iptal et ve pencereyi kapat (Esc)")
        btn_cancel.clicked.connect(self.reject)

        btn_delete = QPushButton("Sil")
        btn_delete.setToolTip("Seçili mesajı kalıcı olarak sil")
        btn_delete.setStyleSheet("""
            QPushButton {
                background-color: rgba(235, 87, 87, 0.22);
                color: #ff6b6b;
                border: 1px solid rgba(235, 87, 87, 0.45);
                border-radius: 8px;
                padding: 6px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #d32f2f;
                color: #ffffff;
            }
        """)
        btn_delete.clicked.connect(self.on_confirm)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_delete)
        layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog {
                background-color: #17212b;
            }
            QPushButton {
                background-color: #242f3d;
                color: #d1dbe5;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 6px 16px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2b5278;
                color: #ffffff;
                border-color: #5288c1;
            }
            QCheckBox {
                color: #e4ecf2;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                background-color: #242f3d;
                border: 1px solid #5288c1;
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background-color: #5288c1;
            }
        """)

    def on_confirm(self):
        self.delete_for_everyone = self.cb_everyone.isChecked()
        self.accept()


class ImageSecurityDialog(QDialog):
    """
    Prompts the user to visually inspect an image before attachment or transmission
    to prevent inadvertent disclosure of physical environment, reflections, barcodes, etc.
    """
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Görsel Güvenlik Kontrolü")
        self.setFixedSize(500, 460)
        self.image_path = image_path
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header = QLabel("🔍 Görsel Güvenlik Denetimi")
        header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        header.setStyleSheet("color: #ffffff;")
        layout.addWidget(header)

        # Image preview
        preview_lbl = QLabel()
        preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_lbl.setStyleSheet("background-color: #0e1621; border: 1px solid #242f3d; border-radius: 8px; padding: 4px;")
        preview_lbl.setFixedHeight(260)

        pix = QPixmap(self.image_path)
        if not pix.isNull():
            scaled = pix.scaled(460, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            preview_lbl.setPixmap(scaled)
        else:
            preview_lbl.setText("Görsel Önizlemesi Yüklenemedi")
            preview_lbl.setStyleSheet("color: #7f91a4;")
        layout.addWidget(preview_lbl)

        # Direct warning box
        warn_box = QFrame()
        warn_box.setStyleSheet("background-color: rgba(245, 176, 65, 0.12); border: 1px solid rgba(245, 176, 65, 0.4); border-radius: 8px; padding: 8px;")
        wb_layout = QVBoxLayout(warn_box)
        wb_layout.setSpacing(4)
        wb_title = QLabel("⚠️ Son Kontrol: Resmi dikkatlice inceleyin.")
        wb_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        wb_title.setStyleSheet("color: #f5b041;")
        wb_layout.addWidget(wb_title)

        wb_sub = QLabel("Sizi ele verebilecek bir detay var mı? (Oda manzarası, pencere, yansıma, priz tipi, fatura, barkod, saat veya hava durumu vb.)")
        wb_sub.setFont(QFont("Segoe UI", 9))
        wb_sub.setStyleSheet("color: #d1dbe5;")
        wb_sub.setWordWrap(True)
        wb_layout.addWidget(wb_sub)
        layout.addWidget(warn_box)

        # Buttons
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("İptal / Vazgeç")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_box.addStretch()

        btn_confirm = QPushButton("İnceledim, Güvenli (Ekle)")
        btn_confirm.setStyleSheet("background-color: #5288c1; color: white; border-radius: 6px; padding: 6px 16px; font-weight: bold;")
        btn_confirm.clicked.connect(self.accept)
        btn_box.addWidget(btn_confirm)

        layout.addLayout(btn_box)


class EmergencyDestructDialog(QDialog):
    """Emergency self-destruct confirmation modal with secure forensic wipe."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🚨 ACİL DURUM İMHASI")
        self.setFixedSize(460, 240)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        header = QLabel("🚨 ACİL DURUM VERİ İMHASI (SELF-DESTRUCT)")
        header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        header.setStyleSheet("color: #ff4d4f;")
        layout.addWidget(header)

        info_lbl = QLabel(
            "⚠️ <b>DİKKAT: Bu işlem geri alınamaz!</b><br><br>"
            "Tüm veritabanı, mesajlar, sohbetler, şifreleme anahtarları ve indirilen medya dosyaları "
            "adli bilişim araçlarıyla (forensics) kurtarılamayacak şekilde diskin üzeri çok katmanlı yazılarak yok edilecek "
            "ve program anında kapatılarak silinecektir."
        )
        info_lbl.setFont(QFont("Segoe UI", 9))
        info_lbl.setStyleSheet("color: #e4ecf2;")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Vazgeç (İptal)")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_layout.addStretch()

        btn_shred = QPushButton("🚨 KALICI OLARAK İMHA ET")
        btn_shred.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: #ffffff;
                border: 1px solid #ff4d4f;
                border-radius: 6px;
                padding: 7px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b71c1c;
            }
        """)
        btn_shred.clicked.connect(self.accept)
        btn_layout.addWidget(btn_shred)

        layout.addLayout(btn_layout)


class UserProfileDialog(QDialog):
    """Telegram-like User Profile & Shared Media drawer/dialog."""
    note_updated = pyqtSignal(str)

    def __init__(self, bot_id: int, chat_id: int, db: DatabaseManager, bot_manager: BotManager, parent=None):
        super().__init__(parent)
        self.bot_id = bot_id
        self.chat_id = chat_id
        self.db = db
        self.bot_manager = bot_manager

        self.setWindowTitle("Kullanıcı Profili ve Paylaşılan Medyalar")
        self.resize(540, 680)
        self.setMinimumSize(460, 560)

        # Trigger async profile refresh from Telegram
        self.bot_manager.profile_fetched.connect(self.on_live_profile_fetched)
        worker = self.bot_manager.get_worker(self.bot_id)
        if worker and worker.isRunning():
            worker.fetch_user_profile_async(self.chat_id)

        self.init_ui()

    def update_dialog_avatar(self, avatar_path: str, name: str):
        if avatar_path and os.path.exists(avatar_path):
            pix = make_circular_pixmap(QPixmap(avatar_path), 70)
            self.avatar_lbl.setText("")
            self.avatar_lbl.setStyleSheet("background: transparent; border: none; padding: 0px;")
            self.avatar_lbl.setPixmap(pix)
            self.avatar_lbl.setToolTip("Görseli açmak için tıklayın")
            make_clickable(self.avatar_lbl, lambda p=avatar_path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
        else:
            initial = name[0].upper() if name and name.strip() and name.strip() != "." else "?"
            self.avatar_lbl.setPixmap(QPixmap())
            self.avatar_lbl.setText(initial)
            self.avatar_lbl.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
            self.avatar_lbl.setCursor(Qt.CursorShape.ArrowCursor)
            self.avatar_lbl.setToolTip("")
            bg_col = get_avatar_color(name)
            self.avatar_lbl.setStyleSheet(f"""
                background-color: {bg_col};
                color: white;
                border-radius: 35px;
                border: none;
            """)

    def on_live_profile_fetched(self, bot_id: int, chat_id: int, data: dict):
        if bot_id != self.bot_id or chat_id != self.chat_id:
            return
        name = data.get("sender_name") or "Kullanıcı"
        if hasattr(self, 'name_lbl'):
            self.name_lbl.setText(name)
        uname = data.get("username")
        if hasattr(self, 'uname_lbl'):
            self.uname_lbl.setText(f"@{uname}" if uname else "Kullanıcı adı yok")
        bio = data.get("bio")
        if hasattr(self, 'bio_content'):
            self.bio_content.setText(bio if bio else "Telegram hesabında biyografi eklenmemiş.")
            self.bio_content.setStyleSheet("color: #ffffff;" if bio else "color: #708499; font-style: italic;")
        avatar_path = data.get("avatar_path") or ""
        if hasattr(self, 'avatar_lbl'):
            self.update_dialog_avatar(avatar_path, name)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        chat = self.db.get_chat(self.bot_id, self.chat_id) or {}
        name = chat.get("sender_name") or "Kullanıcı"
        uname = chat.get("username") or ""
        bio = chat.get("bio") or ""
        note = chat.get("custom_note") or ""
        avatar_path = chat.get("avatar_path") or ""

        # 1. Profile Header Card
        card = QFrame()
        card.setObjectName("profileHeaderCard")
        card.setStyleSheet("#profileHeaderCard { background-color: #17212b; border-radius: 10px; }")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(15, 15, 15, 15)
        card_layout.setSpacing(15)

        # Avatar
        self.avatar_lbl = QLabel()
        self.avatar_lbl.setFixedSize(70, 70)
        self.avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_dialog_avatar(avatar_path, name)
        card_layout.addWidget(self.avatar_lbl)

        # Details
        info_vbox = QVBoxLayout()
        info_vbox.setSpacing(4)

        self.name_lbl = QLabel(name)
        self.name_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.name_lbl.setStyleSheet("color: #ffffff;")
        info_vbox.addWidget(self.name_lbl)

        self.uname_lbl = QLabel(f"@{uname}" if uname else "Kullanıcı adı yok")
        self.uname_lbl.setFont(QFont("Segoe UI", 9))
        self.uname_lbl.setStyleSheet("color: #5288c1;")
        info_vbox.addWidget(self.uname_lbl)

        id_hbox = QHBoxLayout()
        id_hbox.setSpacing(8)
        id_lbl = QLabel(f"ID: {self.chat_id}")
        id_lbl.setFont(QFont("Segoe UI", 9))
        id_lbl.setStyleSheet("color: #9bb7d4;")

        btn_copy = QPushButton("📋 Kopyala")
        btn_copy.setToolTip("Kullanıcı ID'sini panoya kopyala")
        btn_copy.setFixedHeight(26)
        btn_copy.setMinimumWidth(96)
        btn_copy.setStyleSheet("""
            QPushButton {
                background-color: rgba(82, 136, 193, 0.15);
                color: #649ad4;
                border: 1px solid rgba(82, 136, 193, 0.35);
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
                padding: 2px 10px;
            }
            QPushButton:hover {
                background-color: #5288c1;
                color: #ffffff;
            }
        """)
        def on_copy_profile_id():
            QApplication.clipboard().setText(str(self.chat_id))
            QToolTip.showText(btn_copy.mapToGlobal(QPoint(0, 26)), "ID Kopyalandı!", btn_copy)
        btn_copy.clicked.connect(on_copy_profile_id)

        id_hbox.addWidget(id_lbl)
        id_hbox.addWidget(btn_copy)
        id_hbox.addStretch()
        info_vbox.addLayout(id_hbox)

        card_layout.addLayout(info_vbox, 1)
        layout.addWidget(card)

        # 2. Bio / Açıklama & Özel Not Card
        bio_frame = QFrame()
        bio_frame.setObjectName("profileBioFrame")
        bio_frame.setStyleSheet("#profileBioFrame { background-color: #17212b; border: 1px solid #242f3d; border-radius: 12px; }")
        bio_vbox = QVBoxLayout(bio_frame)
        bio_vbox.setContentsMargins(15, 12, 15, 12)
        bio_vbox.setSpacing(8)

        bio_title = QLabel("📌 Telegram Biyografisi / Açıklama:")
        bio_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        bio_title.setStyleSheet("color: #9bb7d4;")
        bio_vbox.addWidget(bio_title)

        bio_text = bio if bio else "Telegram hesabında biyografi eklenmemiş."
        self.bio_content = QLabel(bio_text)
        self.bio_content.setFont(QFont("Segoe UI", 9))
        self.bio_content.setStyleSheet("color: #ffffff;" if bio else "color: #9bb7d4; font-style: italic;")
        self.bio_content.setWordWrap(True)
        bio_vbox.addWidget(self.bio_content)

        # Note Section
        note_row = QHBoxLayout()
        note_row.setContentsMargins(0, 4, 0, 0)
        self.note_disp_lbl = QLabel(f"📝 Sizin Notunuz: <b>{note}</b>" if note else "📝 Sizin Notunuz: <i>(Not eklenmemiş)</i>")
        self.note_disp_lbl.setStyleSheet("color: #e5a93c;")
        btn_edit_note = QPushButton("✏️ Düzenle")
        btn_edit_note.setToolTip("Bu kullanıcı için özel not veya takma ad düzenle")
        btn_edit_note.setFixedHeight(26)
        btn_edit_note.setMinimumWidth(100)
        btn_edit_note.setStyleSheet("""
            QPushButton {
                background-color: rgba(229, 169, 60, 0.15);
                color: #e5a93c;
                border: 1px solid rgba(229, 169, 60, 0.35);
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
                padding: 2px 10px;
            }
            QPushButton:hover {
                background-color: #e5a93c;
                color: #17212b;
            }
        """)
        btn_edit_note.clicked.connect(self.prompt_edit_note)
        note_row.addWidget(self.note_disp_lbl, 1)
        note_row.addWidget(btn_edit_note)
        bio_vbox.addLayout(note_row)

        layout.addWidget(bio_frame)

        # 3. Shared Media Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                background-color: #17212b;
                border: 1px solid #242f3d;
                border-radius: 10px;
            }
            QTabBar::tab {
                background-color: #0e1621;
                color: #7f91a4;
                padding: 8px 18px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: 600;
                font-size: 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #17212b;
                color: #5288c1;
                border-bottom: 2px solid #5288c1;
            }
            QTabBar::tab:hover:!selected {
                background-color: #1c2733;
                color: #ffffff;
            }
        """)

        # Tab 1: Photos & Videos
        tab_media = QWidget()
        media_vbox = QVBoxLayout(tab_media)
        media_vbox.setContentsMargins(10, 10, 10, 10)
        self.load_media_grid(media_vbox)
        self.tabs.addTab(tab_media, "🖼️ Görseller & Videolar")

        # Tab 2: Documents
        tab_docs = QWidget()
        docs_vbox = QVBoxLayout(tab_docs)
        docs_vbox.setContentsMargins(10, 10, 10, 10)
        self.load_documents_list(docs_vbox)
        self.tabs.addTab(tab_docs, "📁 Dosyalar")

        # Tab 3: Voice / Audio
        tab_audio = QWidget()
        audio_vbox = QVBoxLayout(tab_audio)
        audio_vbox.setContentsMargins(10, 10, 10, 10)
        self.load_audio_list(audio_vbox)
        self.tabs.addTab(tab_audio, "🎵 Ses Kayıtları")

        layout.addWidget(self.tabs, 1)

        btn_close = QPushButton("Kapat")
        btn_close.setToolTip("Pencereyi kapat (Esc)")
        btn_close.setFixedHeight(34)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #242f3d;
                color: #d1dbe5;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2b5278;
                color: #ffffff;
                border-color: #5288c1;
            }
        """)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def done(self, r):
        try:
            self.bot_manager.profile_fetched.disconnect(self.on_live_profile_fetched)
        except Exception:
            pass
        super().done(r)

    def prompt_edit_note(self):
        chat = self.db.get_chat(self.bot_id, self.chat_id) or {}
        cur_note = chat.get("custom_note") or ""
        name = chat.get("sender_name") or str(self.chat_id)

        new_note, ok = QInputDialog.getText(self, "Özel Not", f"'{name}' için özel not:", text=cur_note)
        if ok:
            self.db.set_chat_note(self.bot_id, self.chat_id, new_note.strip())
            self.note_disp_lbl.setText(f"📝 Sizin Notunuz: <b>{new_note.strip()}</b>" if new_note.strip() else "📝 Sizin Notunuz: <i>(Not eklenmemiş)</i>")
            self.note_updated.emit(new_note.strip())

    def load_media_grid(self, container_layout: QVBoxLayout):
        all_media = self.db.get_chat_media(self.bot_id, self.chat_id)
        photos = [m for m in all_media if m.get("media_type") in ("photo", "video")]

        if not photos:
            empty_lbl = QLabel("Bu sohbette paylaşılan görsel veya video bulunmuyor.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: #9bb7d4; font-style: italic; padding: 40px;")
            container_layout.addWidget(empty_lbl)
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(10)
        grid.setContentsMargins(4, 4, 4, 4)

        col_count = 3
        for i, item in enumerate(photos):
            m_path = item.get("media_path")
            thumb_frame = QFrame()
            thumb_frame.setStyleSheet("background-color: #242f3d; border-radius: 6px; padding: 4px;")
            tf_vbox = QVBoxLayout(thumb_frame)
            tf_vbox.setContentsMargins(4, 4, 4, 4)
            tf_vbox.setSpacing(4)

            lbl = QLabel()
            lbl.setFixedSize(130, 110)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            if m_path and os.path.exists(m_path):
                pix = QPixmap(m_path)
                if not pix.isNull():
                    lbl.setPixmap(pix.scaled(130, 110, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
                else:
                    lbl.setText("🖼️ Medya")
                lbl.setToolTip("Görseli açmak için tıklayın")
                make_clickable(lbl, lambda p=m_path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
            else:
                lbl.setText("📄 (Silindi)")
                lbl.setStyleSheet("color: #9bb7d4;")

            tf_vbox.addWidget(lbl)

            ts = item.get("timestamp", 0)
            d_str = datetime.fromtimestamp(ts).strftime("%d.%m %H:%M") if ts else ""
            date_lbl = QLabel(d_str)
            date_lbl.setFont(QFont("Segoe UI", 8))
            date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            date_lbl.setStyleSheet("color: #9bb7d4;")
            tf_vbox.addWidget(date_lbl)

            grid.addWidget(thumb_frame, i // col_count, i % col_count)

        scroll.setWidget(grid_widget)
        container_layout.addWidget(scroll)

    def load_documents_list(self, container_layout: QVBoxLayout):
        all_media = self.db.get_chat_media(self.bot_id, self.chat_id)
        docs = [m for m in all_media if m.get("media_type") == "document"]

        if not docs:
            empty_lbl = QLabel("Bu sohbette paylaşılan dosya veya belge bulunmuyor.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: #9bb7d4; font-style: italic; padding: 40px;")
            container_layout.addWidget(empty_lbl)
            return

        list_widget = QListWidget()
        list_widget.setStyleSheet("background: transparent; border: none;")

        for d in docs:
            f_name = d.get("file_name") or "Dosya"
            m_path = d.get("media_path")
            ts = d.get("timestamp", 0)
            d_str = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M") if ts else ""

            row_w = QWidget()
            r_lay = QHBoxLayout(row_w)
            r_lay.setContentsMargins(6, 6, 6, 6)

            icon_lbl = QLabel("📄")
            icon_lbl.setFont(QFont("Segoe UI", 12))

            name_vbox = QVBoxLayout()
            name_vbox.setSpacing(2)
            n_lbl = QLabel(f_name)
            n_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            n_lbl.setStyleSheet("color: #ffffff;")
            t_lbl = QLabel(d_str)
            t_lbl.setFont(QFont("Segoe UI", 8))
            t_lbl.setStyleSheet("color: #9bb7d4;")
            name_vbox.addWidget(n_lbl)
            name_vbox.addWidget(t_lbl)

            r_lay.addWidget(icon_lbl)
            r_lay.addLayout(name_vbox, 1)

            if m_path and os.path.exists(m_path):
                btn_op = QPushButton("Aç")
                btn_op.setToolTip(f"{f_name} dosyasını aç")
                btn_op.setFixedSize(50, 26)
                btn_op.clicked.connect(lambda chk, p=m_path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
                r_lay.addWidget(btn_op)
            else:
                s_lbl = QLabel("(Silindi)")
                s_lbl.setStyleSheet("color: #a0b6cc; font-size: 11px;")
                r_lay.addWidget(s_lbl)

            item = QListWidgetItem(list_widget)
            item.setSizeHint(row_w.sizeHint())
            list_widget.addItem(item)
            list_widget.setItemWidget(item, row_w)

        container_layout.addWidget(list_widget)

    def load_audio_list(self, container_layout: QVBoxLayout):
        all_media = self.db.get_chat_media(self.bot_id, self.chat_id)
        audios = [m for m in all_media if m.get("media_type") in ("voice", "audio")]

        if not audios:
            empty_lbl = QLabel("Bu sohbette paylaşılan ses kaydı bulunmuyor.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("color: #9bb7d4; font-style: italic; padding: 40px;")
            container_layout.addWidget(empty_lbl)
            return

        list_widget = QListWidget()
        list_widget.setStyleSheet("background: transparent; border: none;")

        for a in audios:
            f_name = a.get("file_name") or "Ses Kaydı"
            m_path = a.get("media_path")
            ts = a.get("timestamp", 0)
            d_str = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M") if ts else ""

            row_w = QWidget()
            r_lay = QHBoxLayout(row_w)
            r_lay.setContentsMargins(6, 6, 6, 6)

            icon_lbl = QLabel("🎵")
            icon_lbl.setFont(QFont("Segoe UI", 12))

            name_vbox = QVBoxLayout()
            name_vbox.setSpacing(2)
            n_lbl = QLabel(f_name)
            n_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            n_lbl.setStyleSheet("color: #ffffff;")
            t_lbl = QLabel(d_str)
            t_lbl.setFont(QFont("Segoe UI", 8))
            t_lbl.setStyleSheet("color: #9bb7d4;")
            name_vbox.addWidget(n_lbl)
            name_vbox.addWidget(t_lbl)

            r_lay.addWidget(icon_lbl)
            r_lay.addLayout(name_vbox, 1)

            if m_path and os.path.exists(m_path):
                btn_op = QPushButton("Dinle / Aç")
                btn_op.setToolTip(f"{f_name} ses kaydını dinle/aç")
                btn_op.setFixedHeight(26)
                btn_op.setMinimumWidth(95)
                btn_op.setStyleSheet("padding: 2px 8px;")
                btn_op.clicked.connect(lambda chk, p=m_path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
                r_lay.addWidget(btn_op)
            else:
                s_lbl = QLabel("(Silindi)")
                s_lbl.setStyleSheet("color: #a0b6cc; font-size: 11px;")
                r_lay.addWidget(s_lbl)

            item = QListWidgetItem(list_widget)
            item.setSizeHint(row_w.sizeHint())
            list_widget.addItem(item)
            list_widget.setItemWidget(item, row_w)

        container_layout.addWidget(list_widget)


class BotManageDialog(QDialog):
    """Dialog to manage multiple bots."""
    bots_updated = pyqtSignal()

    def __init__(self, db: DatabaseManager, bot_manager: BotManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.bot_manager = bot_manager
        self.setWindowTitle("Bot Yönetimi")
        self.resize(680, 420)
        self.init_ui()
        self.load_bots()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Hayati Anonimlik Uyarısı (Bot Hesabı Uyarısı)
        warn_box = QFrame()
        warn_box.setStyleSheet("""
            background-color: rgba(245, 176, 65, 0.12);
            border: 1px solid rgba(245, 176, 65, 0.4);
            border-radius: 8px;
            padding: 8px;
        """)
        wb_layout = QVBoxLayout(warn_box)
        wb_lbl = QLabel(
            "⚠️ <b>Hayati Anonimlik Uyarısı:</b> Telegram botunuzu kesinlikle kendi kişisel telefon numaranıza bağlı "
            "hesabınızdan veya ev internetinizden oluşturmayın! Botu oluşturan hesap tespit edilirse tüm anonimlik çöker. "
            "Anonim/kullan-at bir Telegram hesabı ile BotFather üzerinden bot oluşturun."
        )
        wb_lbl.setWordWrap(True)
        wb_lbl.setStyleSheet("color: #f5b041; font-size: 11px;")
        wb_layout.addWidget(wb_lbl)
        layout.addWidget(warn_box)

        form_frame = QFrame()
        form_frame.setStyleSheet("""
            QFrame {
                background-color: #17212b;
                border: 1px solid #242f3d;
                border-radius: 10px;
                padding: 10px;
            }
            QLineEdit {
                background-color: #242f3d;
                color: #ffffff;
                border: 1px solid #2b394a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                background-color: #1c2733;
                border: 1px solid #5288c1;
            }
            QPushButton {
                background-color: #5288c1;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #649ad4;
            }
        """)
        form_layout = QVBoxLayout(form_frame)

        title = QLabel("Yeni Bot Ekle")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        form_layout.addWidget(title)

        inputs_layout = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Bot Adı/Etiket (örn: Anonim Bot 1)")
        self.name_input.setToolTip("Botunuz için anlaşılır bir etiket veya takma ad")

        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("BotFather Token")
        self.token_input.setToolTip("Telegram @BotFather botundan aldığınız API Token (örn: 123456:ABC-DEF...)")

        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("Proxy (örn: socks5h://127.0.0.1:9050)")
        self.proxy_input.setToolTip("İsteğe bağlı: Tor veya SOCKS5/HTTP proxy adresi (örn: socks5h://127.0.0.1:9050)")

        btn_add = QPushButton("+ Ekle ve Başlat")
        btn_add.setToolTip("Yeni botu sisteme kaydet ve Telegram API ile bağlantı kur")
        btn_add.clicked.connect(self.add_bot)

        inputs_layout.addWidget(self.name_input)
        inputs_layout.addWidget(self.token_input)
        inputs_layout.addWidget(self.proxy_input)
        inputs_layout.addWidget(btn_add)
        form_layout.addLayout(inputs_layout)

        layout.addWidget(form_frame)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Ad", "Kullanıcı Adı", "Proxy", "İşlem"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #17212b;
                color: #ffffff;
                gridline-color: #242f3d;
                border: 1px solid #242f3d;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #242f3d;
                color: #d1dbe5;
                font-weight: 600;
                padding: 6px;
                border: none;
                border-right: 1px solid #1c2733;
                border-bottom: 1px solid #1c2733;
            }
        """)
        layout.addWidget(self.table)

        self.empty_bots_lbl = QLabel("ℹ️ Henüz kayıtlı Telegram botu yok. Yukarıdaki formdan BotFather API token'ınızı girerek ilk botunuzu ekleyin.")
        self.empty_bots_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_bots_lbl.setStyleSheet("color: #9bb7d4; font-style: italic; padding: 10px;")
        layout.addWidget(self.empty_bots_lbl)

    def load_bots(self):
        self.table.setRowCount(0)
        bots = self.db.get_bots()
        self.empty_bots_lbl.setVisible(len(bots) == 0)
        for bot in bots:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(bot["id"])))
            self.table.setItem(r, 1, QTableWidgetItem(bot.get("name") or "İsimsiz"))
            self.table.setItem(r, 2, QTableWidgetItem(bot.get("username") or "-"))
            self.table.setItem(r, 3, QTableWidgetItem(bot.get("proxy") or "Doğrudan"))

            btn_del = QPushButton("Sil")
            btn_del.setToolTip("Bu botu sistemden sil")
            btn_del.setStyleSheet("""
                QPushButton {
                    background-color: rgba(235, 87, 87, 0.2);
                    color: #ff6b6b;
                    border: 1px solid rgba(235, 87, 87, 0.4);
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #c62828;
                    color: #ffffff;
                }
            """)
            bot_id = bot["id"]
            btn_del.clicked.connect(lambda checked, bid=bot_id: self.delete_bot(bid))
            self.table.setCellWidget(r, 4, btn_del)

    def add_bot(self):
        name = self.name_input.text().strip()
        token = self.token_input.text().strip()
        proxy = self.proxy_input.text().strip()

        if not token:
            QMessageBox.warning(self, "Hata", "Lütfen bir Bot Token girin.")
            return

        bot_id = self.db.add_bot(token=token, name=name or "Bot", username="", proxy=proxy)
        self.bot_manager.start_bot(bot_id=bot_id, token=token, proxy=proxy or None)

        self.name_input.clear()
        self.token_input.clear()
        self.proxy_input.clear()

        self.load_bots()
        self.bots_updated.emit()

    def delete_bot(self, bot_id: int):
        reply = QMessageBox.question(self, "Onay", "Bu botu ve ayarlarını kaldırmak istediğinize emin misiniz?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.bot_manager.stop_bot(bot_id)
            self.db.delete_bot(bot_id)
            self.load_bots()
            self.bots_updated.emit()


class ChatWallpaperWidget(QWidget):
    """Telegram styled subtle doodle wallpaper canvas."""
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0e1621"))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 8), 1))

        w, h = self.width(), self.height()
        step = 68
        for x in range(0, w, step):
            for y in range(0, h, step):
                # Subtle repeating geometric motifs
                p.drawEllipse(x + 14, y + 14, 5, 5)
                p.drawLine(x + 36, y + 26, x + 36, y + 36)
                p.drawLine(x + 31, y + 31, x + 41, y + 31)
                p.drawRect(x + 52, y + 48, 4, 4)
        p.end()


class AudioPlayerWidget(QFrame):
    """Telegram styled voice/audio playback widget with Play/Pause, Progress Slider, and Duration."""
    _active_player = None

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.setObjectName("audioPlayerWidget")
        self.setStyleSheet("""
            QFrame#audioPlayerWidget {
                background-color: rgba(0, 0, 0, 0.22);
                border-radius: 10px;
            }
            QPushButton#btnPlayPause {
                background-color: #5288c1;
                color: white;
                border-radius: 16px;
                font-size: 13px;
                font-weight: bold;
                border: none;
            }
            QPushButton#btnPlayPause:hover {
                background-color: #649ad4;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: rgba(255, 255, 255, 0.18);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #5288c1;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 10px;
                margin-top: -3px;
                margin-bottom: -3px;
                border-radius: 5px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 10, 6)
        layout.setSpacing(10)

        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("btnPlayPause")
        self.btn_play.setToolTip("Oynat / Duraklat (Boşluk tuşu)")
        self.btn_play.setFixedSize(32, 32)
        self.btn_play.clicked.connect(self.toggle_playback)
        layout.addWidget(self.btn_play)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setToolTip("Süre çubuğu (İleri/Geri sar)")
        self.slider.setRange(0, 100)
        self.slider.sliderMoved.connect(self.seek_position)
        info_layout.addWidget(self.slider)

        sub_layout = QHBoxLayout()
        sub_layout.setContentsMargins(0, 0, 0, 0)
        self.time_lbl = QLabel("0:00")
        self.time_lbl.setFont(QFont("Segoe UI", 8))
        self.time_lbl.setStyleSheet("color: #9bb7d4;")
        sub_layout.addWidget(self.time_lbl)
        sub_layout.addStretch()

        f_name = Path(file_path).name
        self.title_lbl = QLabel(f_name[:24] + "..." if len(f_name) > 24 else f_name)
        self.title_lbl.setFont(QFont("Segoe UI", 8))
        self.title_lbl.setStyleSheet("color: #a0b6cc;")
        self.title_lbl.setToolTip(f_name)
        sub_layout.addWidget(self.title_lbl)

        info_layout.addLayout(sub_layout)
        layout.addLayout(info_layout, 1)

        self.player = None
        self.audio_output = None
        self.duration_ms = 0

    def _init_player(self):
        if self.player is None:
            self.player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.player.setAudioOutput(self.audio_output)
            self.player.setSource(QUrl.fromLocalFile(self.file_path))
            self.player.positionChanged.connect(self.on_position_changed)
            self.player.durationChanged.connect(self.on_duration_changed)
            self.player.playbackStateChanged.connect(self.on_state_changed)

    def toggle_playback(self):
        self._init_player()
        if AudioPlayerWidget._active_player and AudioPlayerWidget._active_player != self:
            try:
                AudioPlayerWidget._active_player.pause()
            except Exception:
                pass

        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.duration_ms > 0 and self.player.position() >= self.duration_ms - 200:
                self.player.setPosition(0)
            AudioPlayerWidget._active_player = self
            self.player.play()

    def pause(self):
        if self.player and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()

    def on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("⏸")
        else:
            self.btn_play.setText("▶")

    def on_duration_changed(self, duration):
        self.duration_ms = duration
        self.slider.setRange(0, max(1, duration))
        self.update_time_label(self.player.position(), duration)

    def on_position_changed(self, pos):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self.update_time_label(pos, self.duration_ms)

    def seek_position(self, pos):
        self._init_player()
        if self.player:
            self.player.setPosition(pos)

    def stop_and_release(self):
        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        if AudioPlayerWidget._active_player == self:
            AudioPlayerWidget._active_player = None

    def closeEvent(self, event):
        self.stop_and_release()
        super().closeEvent(event)

    def update_time_label(self, pos, duration):
        cur_s = pos // 1000
        dur_s = duration // 1000
        self.time_lbl.setText(f"{cur_s // 60}:{cur_s % 60:02d} / {dur_s // 60}:{dur_s % 60:02d}")


class EmojiPickerPopup(QFrame):
    """Categorized Telegram emoji picker popover."""
    emoji_selected = pyqtSignal(str)

    EMOJI_LIST = [
        "😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣", "😊", "😇",
        "🙂", "😉", "😍", "🥰", "😘", "😋", "😛", "😎", "🤩", "🥳",
        "🤔", "🤫", "🤭", "🤐", "😴", "😭", "😢", "😤", "😡", "😱",
        "🥺", "😳", "😬", "🙄", "👍", "👎", "👏", "🙌", "🤝", "🙏",
        "✌️", "🤞", "🤙", "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤",
        "💔", "🔥", "💯", "🎉", "✨", "⭐", "🚀", "💡", "⚠️", "✅"
    ]

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("emojiPickerPopup")
        self.setStyleSheet("""
            QFrame#emojiPickerPopup {
                background-color: #17212b;
                border: 1px solid rgba(82, 136, 193, 0.35);
                border-radius: 12px;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 6px;
                font-family: 'Segoe UI Emoji', 'Noto Color Emoji', 'Apple Color Emoji', sans-serif;
                font-size: 18px;
                font-weight: normal;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #242f3d;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header_layout = QHBoxLayout()
        header_lbl = QLabel("😊 Emojiler")
        header_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        header_lbl.setStyleSheet("color: #9bb7d4;")
        header_layout.addWidget(header_lbl)
        header_layout.addStretch()

        btn_close = QPushButton("✕")
        btn_close.setToolTip("Kapat (Esc)")
        btn_close.setFixedSize(20, 20)
        btn_close.clicked.connect(self.close)
        header_layout.addWidget(btn_close)
        layout.addLayout(header_layout)

        grid = QGridLayout()
        grid.setSpacing(3)
        cols = 10
        for idx, em in enumerate(self.EMOJI_LIST):
            btn = QPushButton(em)
            btn.setToolTip(f"{em} Ekle")
            btn.setFixedSize(32, 32)
            btn.clicked.connect(lambda _, e=em: self._on_select(e))
            grid.addWidget(btn, idx // cols, idx % cols)

        layout.addLayout(grid)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _on_select(self, em: str):
        self.emoji_selected.emit(em)


def is_emoji_only(text: str) -> bool:
    """Returns True if text consists purely of 1 to 3 emojis and whitespace."""
    if not text or not isinstance(text, str):
        return False
    stripped = text.strip()
    if not stripped:
        return False
    pattern = re.compile(
        r'^('
        r'[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50-\u2b55\ufe00-\ufe0f\u200d\u20e3\s]'
        r')+$'
    )
    if not pattern.match(stripped):
        return False
    count = len(re.findall(r'[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50-\u2b55]', stripped))
    return 1 <= count <= 3


class TelegramAnimatedEmojiWidget(QWidget):
    """Telegram-style large interactive animated emoji with spring/bounce scale animation.
    - Scales up from 0.2 to 1.25, then settles to 1.0 using OutBack curve.
    - Interactive: Clicking re-triggers the bounce animation.
    - Rendered with high-DPI antialiasing and crisp emoji font sizing.
    """
    clicked = pyqtSignal()

    def __init__(self, emoji_text: str, parent=None):
        super().__init__(parent)
        self.emoji_text = emoji_text.strip()
        count = len(re.findall(r'[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50-\u2b55]', self.emoji_text))

        # Telegram-proportional sizing based on emoji count
        if count == 1:
            self.font_size = 46
            self.setFixedSize(92, 92)
        elif count == 2:
            self.font_size = 36
            self.setFixedSize(124, 82)
        else:
            self.font_size = 30
            self.setFixedSize(148, 74)

        self._scale = 0.2
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.anim = QVariantAnimation(self)
        self.anim.setDuration(450)
        self.anim.setStartValue(0.2)
        self.anim.setKeyValueAt(0.65, 1.25)
        self.anim.setKeyValueAt(0.85, 0.92)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.anim.valueChanged.connect(self._on_anim_value)

        # Start animation shortly after creation
        QTimer.singleShot(20, self.start_animation)

    def start_animation(self):
        self.anim.stop()
        self.anim.setStartValue(0.2)
        self.anim.start()

    def bounce(self):
        """Replay Telegram bounce heartbeat animation on user click."""
        self.anim.stop()
        self.anim.setStartValue(0.7)
        self.anim.start()

    def _on_anim_value(self, val):
        self._scale = float(val)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.bounce()
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        parent_widget = self.parent()
        if parent_widget and hasattr(parent_widget, "mouseDoubleClickEvent"):
            parent_widget.mouseDoubleClickEvent(event)
        else:
            super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        font = QFont()
        font.setFamilies(["Segoe UI Emoji", "Noto Color Emoji", "Apple Color Emoji", "Segoe UI Symbol"])
        font.setPointSize(self.font_size)
        painter.setFont(font)

        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.emoji_text)
        painter.end()


class TelegramTickWidget(QWidget):
    """Crisp vector anti-aliased Telegram tick marks:
    - Single tick (is_read=False): Muted blue-gray ✓ for delivered/sent.
    - Double tick (is_read=True): Telegram green ✓✓ for read/seen.
    - Clickable: Clicking the tick toggles read status immediately.
    """
    clicked = pyqtSignal()

    def __init__(self, is_read: bool = False, parent=None):
        super().__init__(parent)
        self.is_read = is_read
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(18 if is_read else 13, 15)
        self.setToolTip("✓✓ Görüldü (Okundu)\n(İletildi yapmak için tıklayın)" if is_read else "✓ İletildi (Henüz bakılmadı)\n(Okundu yapmak için tıklayın)")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def set_read(self, is_read: bool):
        self.is_read = is_read
        self.setFixedSize(18 if is_read else 13, 15)
        self.setToolTip("✓✓ Görüldü (Okundu)\n(İletildi yapmak için tıklayın)" if is_read else "✓ İletildi (Henüz bakılmadı)\n(Okundu yapmak için tıklayın)")
        self.updateGeometry()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.is_read:
            pen = QPen(QColor("#4cd964"), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            # Left check
            p1 = QPainterPath()
            p1.moveTo(QPointF(1.5, 7.5))
            p1.lineTo(QPointF(4.8, 10.8))
            p1.lineTo(QPointF(11.2, 3.5))
            p.drawPath(p1)
            # Right check (tightly spaced, authentic Telegram desktop style)
            p2 = QPainterPath()
            p2.moveTo(QPointF(5.8, 7.5))
            p2.lineTo(QPointF(9.1, 10.8))
            p2.lineTo(QPointF(15.2, 3.5))
            p.drawPath(p2)
        else:
            pen = QPen(QColor("#b0d3f8"), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            # Single check (clean and crisp)
            p1 = QPainterPath()
            p1.moveTo(QPointF(1.5, 7.5))
            p1.lineTo(QPointF(4.8, 10.8))
            p1.lineTo(QPointF(10.5, 3.5))
            p.drawPath(p1)
        p.end()


class MessageBubbleWidget(QFrame):
    """Telegram styled message bubble with reply quote, media, and context menu."""
    request_reply = pyqtSignal(dict)
    request_edit = pyqtSignal(dict)
    request_delete_dialog = pyqtSignal(dict)
    request_delete_media_file = pyqtSignal(int)
    request_toggle_deleted_by_sender = pyqtSignal(dict)
    request_toggle_read_status = pyqtSignal(int, bool)
    request_reaction = pyqtSignal(dict, str)
    request_jump_to_message = pyqtSignal(str)

    def __init__(self, msg_data: dict):
        super().__init__()
        self.msg_data = msg_data
        self.is_outgoing = bool(msg_data.get("is_outgoing"))
        self.is_read = bool(msg_data.get("is_read"))
        self.reaction = msg_data.get("reactions") or ""
        self.db_id = msg_data.get("id")
        self.tick_widget = None
        self.emoji_widget = None
        self.reply_frame = None

        self.setObjectName("messageBubble")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.setMaximumWidth(520)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        ts = msg_data.get("timestamp") or int(time.time())
        time_str = datetime.fromtimestamp(ts).strftime("%H:%M")

        is_deleted_by_sender = bool(msg_data.get("is_deleted_by_sender"))
        is_edited = bool(msg_data.get("is_edited"))
        reply_to_text = msg_data.get("reply_to_text")
        self.reply_to_text = reply_to_text
        media_type = msg_data.get("media_type")
        media_path = msg_data.get("media_path")
        file_name = msg_data.get("file_name") or "Dosya"
        text = msg_data.get("text") or ""

        font = QFont()
        font.setFamilies(["Segoe UI", "Segoe UI Emoji", "Noto Color Emoji", "Apple Color Emoji"])
        font.setPointSize(10)
        fm = QFontMetrics(font)
        text_advance = fm.horizontalAdvance(text) if text else 0
        has_url = bool(re.search(r'https?://[^\s]+', text))
        has_complex_elements = (is_deleted_by_sender or is_edited or bool(reply_to_text) or bool(media_type) or has_url)
        is_standalone_emoji = (not has_complex_elements and is_emoji_only(text))
        self.is_standalone_emoji = is_standalone_emoji
        is_single_line = (not is_standalone_emoji and not has_complex_elements and not bool(self.reaction) and bool(text) and ("\n" not in text) and (text_advance + 80 < 480))

        if is_standalone_emoji:
            # Borderless Telegram animated emoji with semi-transparent time/tick pill
            layout = QVBoxLayout(self)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.setSpacing(2)

            self.emoji_widget = TelegramAnimatedEmojiWidget(text)
            self.emoji_widget.clicked.connect(self._on_emoji_clicked)
            layout.addWidget(self.emoji_widget, 0, Qt.AlignmentFlag.AlignCenter)

            if self.reaction:
                rx_btn = QPushButton(f"{self.reaction}  1")
                rx_btn.setFixedHeight(24)
                rx_btn.setToolTip("Tepkiyi kaldır")
                rx_btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(43, 82, 120, 0.7);
                        border: 1px solid #5288c1;
                        border-radius: 12px;
                        padding: 0px 8px 1px 8px;
                        font-family: 'Segoe UI Emoji', 'Noto Color Emoji', 'Apple Color Emoji', 'Segoe UI', sans-serif;
                        font-size: 13px;
                        font-weight: normal;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: rgba(43, 82, 120, 0.9);
                    }
                """)
                rx_btn.clicked.connect(lambda: self.toggle_reaction(self.reaction))
                layout.addWidget(rx_btn, 0, Qt.AlignmentFlag.AlignCenter)

            pill = QFrame()
            pill.setObjectName("emojiTimePill")
            pill_layout = QHBoxLayout(pill)
            pill_layout.setContentsMargins(6, 2, 6, 2)
            pill_layout.setSpacing(4)

            time_label = QLabel(time_str)
            time_label.setFont(QFont("Segoe UI", 8))
            pill_layout.addWidget(time_label)

            if self.is_outgoing:
                self.tick_widget = TelegramTickWidget(is_read=self.is_read)
                self.tick_widget.clicked.connect(self.toggle_read_status)
                pill_layout.addWidget(self.tick_widget)
                time_label.setStyleSheet("color: #b0d3f8;")
            else:
                time_label.setStyleSheet("color: #d1dbe5;")

            pill.setStyleSheet("""
                QFrame#emojiTimePill {
                    background-color: rgba(15, 23, 33, 0.72);
                    border-radius: 9px;
                }
            """)

            pill_row = QHBoxLayout()
            pill_row.setContentsMargins(0, 0, 0, 0)
            if self.is_outgoing:
                pill_row.addStretch()
                pill_row.addWidget(pill)
            else:
                pill_row.addWidget(pill)
                pill_row.addStretch()
            layout.addLayout(pill_row)

            self.setStyleSheet("""
                QFrame#messageBubble {
                    background-color: transparent;
                    border: none;
                }
                QFrame#messageBubble:hover {
                    background-color: transparent;
                }
            """)

        elif is_single_line:
            # Inline horizontal Telegram bubble (e.g. short greetings)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(12, 6, 10, 6)
            layout.setSpacing(10)

            text_label = QLabel(text)
            text_label.setFont(font)
            text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            text_label.mouseDoubleClickEvent = lambda e: self.mouseDoubleClickEvent(e)
            layout.addWidget(text_label)

            time_layout = QHBoxLayout()
            time_layout.setContentsMargins(0, 0, 0, 0)
            time_layout.setSpacing(3)
            time_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)

            time_label = QLabel(time_str)
            time_label.setFont(QFont("Segoe UI", 8))
            time_layout.addWidget(time_label)

            if self.is_outgoing:
                self.tick_widget = TelegramTickWidget(is_read=self.is_read)
                self.tick_widget.clicked.connect(self.toggle_read_status)
                time_layout.addWidget(self.tick_widget)
                time_label.setStyleSheet("color: #8ab6e0;")
                self.setStyleSheet("""
                    QFrame#messageBubble {
                        background-color: #2b5278;
                        border-radius: 14px;
                        border-bottom-right-radius: 3px;
                    }
                    QFrame#messageBubble:hover {
                        background-color: #315c86;
                    }
                    QLabel { color: #ffffff; }
                """)
            else:
                time_label.setStyleSheet("color: #708499;")
                self.setStyleSheet("""
                    QFrame#messageBubble {
                        background-color: #182533;
                        border-radius: 14px;
                        border-bottom-left-radius: 3px;
                    }
                    QFrame#messageBubble:hover {
                        background-color: #1f2d3d;
                    }
                    QLabel { color: #f5f5f5; }
                """)

            layout.addLayout(time_layout)

        else:
            # Multi-line / Rich content Telegram bubble
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 8, 12, 7)
            layout.setSpacing(5)

            # 0. Deleted by Sender Banner
            if is_deleted_by_sender:
                del_banner = QLabel("⚠️ Karşı taraf bu mesajı sildi (Yerel kopya korunuyor)")
                del_banner.setStyleSheet("""
                    background-color: rgba(235, 87, 87, 0.15);
                    color: #ff7b88;
                    border: 1px solid rgba(235, 87, 87, 0.35);
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-weight: bold;
                    font-size: 10px;
                """)
                layout.addWidget(del_banner)

            # 0.1 Edited by Sender Banner
            if is_edited:
                orig = msg_data.get("original_text") or ""
                edit_text = "✏️ Karşı taraf bu mesajı düzenledi"
                if orig:
                    edit_text += f"\nOrijinal: \"{orig[:60]}...\"" if len(orig) > 60 else f"\nOrijinal: \"{orig}\""
                edit_banner = QLabel(edit_text)
                edit_banner.setStyleSheet("""
                    background-color: rgba(242, 153, 74, 0.15);
                    color: #ffb865;
                    border: 1px solid rgba(242, 153, 74, 0.35);
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 10px;
                """)
                layout.addWidget(edit_banner)

            # 1. Reply Quote
            if reply_to_text:
                self.reply_frame = QFrame()
                self.reply_frame.setObjectName("replyQuoteFrame")
                self.reply_frame.setStyleSheet("""
                    QFrame#replyQuoteFrame {
                        background-color: rgba(0, 0, 0, 0.22);
                        border-left: 3px solid #5288c1;
                        border-radius: 4px;
                    }
                    QFrame#replyQuoteFrame:hover {
                        background-color: rgba(82, 136, 193, 0.25);
                    }
                """)
                self.reply_frame.setCursor(Qt.CursorShape.PointingHandCursor)
                self.reply_frame.setToolTip("Yanıtlanan mesaja git (Tıkla)")
                make_clickable(self.reply_frame, lambda t=reply_to_text: self.request_jump_to_message.emit(t))

                rf_layout = QVBoxLayout(self.reply_frame)
                rf_layout.setContentsMargins(8, 4, 8, 4)
                rf_layout.setSpacing(2)

                rep_title = QLabel("Yanıt")
                rep_title.setStyleSheet("color: #5288c1; font-weight: bold; font-size: 11px;")
                make_clickable(rep_title, lambda t=reply_to_text: self.request_jump_to_message.emit(t))
                rf_layout.addWidget(rep_title)

                clean_rep = reply_to_text[:70] + "..." if len(reply_to_text) > 70 else reply_to_text
                rep_lbl = QLabel(clean_rep)
                rep_font = QFont()
                rep_font.setFamilies(["Segoe UI Emoji", "Noto Color Emoji", "Apple Color Emoji", "Segoe UI", "sans-serif"])
                if is_emoji_only(clean_rep):
                    rep_font.setPointSize(14)
                else:
                    rep_font.setPointSize(10)
                rep_lbl.setFont(rep_font)
                rep_lbl.setStyleSheet("color: #d1dbe5; padding-right: 4px;")
                make_clickable(rep_lbl, lambda t=reply_to_text: self.request_jump_to_message.emit(t))
                rf_layout.addWidget(rep_lbl)

                layout.addWidget(self.reply_frame)

            # 2. Media Preview
            if media_type == "photo" and media_path and os.path.exists(media_path):
                img_label = QLabel()
                pixmap = QPixmap(media_path)
                if not pixmap.isNull():
                    scaled_pix = pixmap.scaled(320, 320, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    img_label.setPixmap(scaled_pix)
                    img_label.setStyleSheet("border-radius: 8px;")
                    img_label.setToolTip("Görseli açmak için tıklayın")
                    make_clickable(img_label, lambda: self.open_file(media_path))
                    layout.addWidget(img_label)

            elif media_type in ("voice", "audio") and media_path and os.path.exists(media_path):
                # Sleek voice/audio waveform player
                player_bar = AudioPlayerWidget(media_path)
                layout.addWidget(player_bar)

            elif media_type and media_path and os.path.exists(media_path):
                file_bar = QFrame()
                file_bar.setObjectName("bubbleFileBar")
                file_bar.setStyleSheet("""
                    QFrame#bubbleFileBar {
                        background-color: rgba(0, 0, 0, 0.2);
                        border-radius: 8px;
                    }
                    QPushButton {
                        background-color: #5288c1;
                        color: white;
                        border-radius: 4px;
                        padding: 3px 10px;
                        font-size: 11px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #649ad4;
                    }
                """)
                f_layout = QHBoxLayout(file_bar)
                f_layout.setContentsMargins(8, 5, 8, 5)

                icon_text = "🎥" if media_type == "video" else "📄"
                f_label = QLabel(f"{icon_text}  {file_name}")
                f_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                f_label.setStyleSheet("color: #ffffff;")
                f_layout.addWidget(f_label)

                btn_open = QPushButton("Aç")
                btn_open.setToolTip(f"{file_name} dosyasını varsayılan uygulamada aç")
                btn_open.clicked.connect(lambda: self.open_file(media_path))
                f_layout.addWidget(btn_open)

                layout.addWidget(file_bar)

            elif media_type and not (media_path and os.path.exists(media_path)):
                del_lbl = QLabel(f"📄 [{file_name}] - (Dosya diskten silindi)")
                del_lbl.setStyleSheet("color: #a0b6cc; font-style: italic;")
                layout.addWidget(del_lbl)

            # 3. Text Message
            if text:
                text_label = QLabel(text)
                text_label.setWordWrap(True)
                text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                text_label.mouseDoubleClickEvent = lambda e: self.mouseDoubleClickEvent(e)
                text_label.setFont(font)
                text_label.setMaximumWidth(480)
                layout.addWidget(text_label)

                # Link Preview Card if text has URL
                url_match = re.search(r'https?://[^\s]+', text)
                if url_match:
                    found_url = url_match.group(0)
                    try:
                        parsed_host = urlparse(found_url).netloc
                        if parsed_host:
                            link_card = QFrame()
                            link_card.setObjectName("linkPreviewCard")
                            link_card.setStyleSheet("""
                                QFrame#linkPreviewCard {
                                    background-color: rgba(0, 0, 0, 0.22);
                                    border-left: 3px solid #5288c1;
                                    border-radius: 4px;
                                }
                            """)
                            lc_layout = QVBoxLayout(link_card)
                            lc_layout.setContentsMargins(8, 4, 8, 4)
                            lc_layout.setSpacing(2)
                            host_lbl = QLabel(f"🔗 {parsed_host}")
                            host_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                            host_lbl.setStyleSheet("color: #5288c1;")
                            url_lbl = QLabel(found_url[:50] + "..." if len(found_url) > 50 else found_url)
                            url_lbl.setFont(QFont("Segoe UI", 8))
                            url_lbl.setStyleSheet("color: #9bb7d4; text-decoration: underline;")
                            make_clickable(link_card, lambda u=found_url: safe_open_url(u))
                            lc_layout.addWidget(host_lbl)
                            lc_layout.addWidget(url_lbl)
                            layout.addWidget(link_card)
                    except Exception:
                        pass

            # Reaction badge pill (if present)
            if self.reaction:
                rx_btn = QPushButton(f"{self.reaction}  1")
                rx_btn.setFixedHeight(24)
                rx_btn.setToolTip("Tepkiyi kaldır")
                rx_btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(43, 82, 120, 0.55);
                        border: 1px solid #5288c1;
                        border-radius: 12px;
                        padding: 0px 8px 1px 8px;
                        font-family: 'Segoe UI Emoji', 'Noto Color Emoji', 'Apple Color Emoji', 'Segoe UI', sans-serif;
                        font-size: 13px;
                        font-weight: normal;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: rgba(43, 82, 120, 0.85);
                    }
                """)
                rx_btn.clicked.connect(lambda: self.toggle_reaction(self.reaction))
                layout.addWidget(rx_btn, alignment=Qt.AlignmentFlag.AlignLeft)

            # 4. Bottom Info: Timestamp & Telegram Checkmarks
            bottom_layout = QHBoxLayout()
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            bottom_layout.setSpacing(4)
            bottom_layout.addStretch(1)

            time_label = QLabel(time_str)
            time_label.setFont(QFont("Segoe UI", 8))
            bottom_layout.addWidget(time_label)

            if self.is_outgoing:
                self.tick_widget = TelegramTickWidget(is_read=self.is_read)
                self.tick_widget.clicked.connect(self.toggle_read_status)
                bottom_layout.addWidget(self.tick_widget)
                time_label.setStyleSheet("color: #8ab6e0;")
                self.setStyleSheet("""
                    QFrame#messageBubble {
                        background-color: #2b5278;
                        border-radius: 14px;
                        border-bottom-right-radius: 3px;
                    }
                    QFrame#messageBubble:hover {
                        background-color: #315c86;
                    }
                    QLabel { color: #ffffff; }
                """)
            else:
                time_label.setStyleSheet("color: #708499;")
                self.setStyleSheet("""
                    QFrame#messageBubble {
                        background-color: #182533;
                        border-radius: 14px;
                        border-bottom-left-radius: 3px;
                    }
                    QFrame#messageBubble:hover {
                        background-color: #1f2d3d;
                    }
                    QLabel { color: #f5f5f5; }
                """)

            layout.addLayout(bottom_layout)

    def _on_emoji_clicked(self):
        """Interactive emoji click handler."""
        pass

    def _apply_normal_bubble_style(self):
        if getattr(self, "is_standalone_emoji", False):
            self.setStyleSheet("""
                QFrame#messageBubble {
                    background-color: transparent;
                    border: none;
                }
                QFrame#messageBubble:hover {
                    background-color: transparent;
                }
            """)
        elif self.is_outgoing:
            self.setStyleSheet("""
                QFrame#messageBubble {
                    background-color: #2b5278;
                    border-radius: 14px;
                    border-bottom-right-radius: 3px;
                }
                QFrame#messageBubble:hover {
                    background-color: #315c86;
                }
                QLabel { color: #ffffff; }
            """)
        else:
            self.setStyleSheet("""
                QFrame#messageBubble {
                    background-color: #182533;
                    border-radius: 14px;
                    border-bottom-left-radius: 3px;
                }
                QFrame#messageBubble:hover {
                    background-color: #1f2d3d;
                }
                QLabel { color: #f5f5f5; }
            """)

    def flash_highlight(self):
        """Telegram-style smooth light pulse / flash highlight on bubble when jumped to."""
        if hasattr(self, "_flash_anim") and self._flash_anim.state() == QVariantAnimation.State.Running:
            self._flash_anim.stop()

        self._flash_anim = QVariantAnimation(self)
        self._flash_anim.setDuration(1200)
        self._flash_anim.setStartValue(0.0)
        self._flash_anim.setKeyValueAt(0.25, 1.0)
        self._flash_anim.setKeyValueAt(0.60, 0.65)
        self._flash_anim.setEndValue(0.0)
        self._flash_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._flash_anim.valueChanged.connect(self._on_flash_step)
        self._flash_anim.finished.connect(self._apply_normal_bubble_style)
        self._flash_anim.start()

    def _on_flash_step(self, val):
        t = float(val)
        if getattr(self, "is_standalone_emoji", False):
            alpha_bg = t * 0.45
            alpha_border = t * 0.95
            self.setStyleSheet(f"""
                QFrame#messageBubble {{
                    background-color: rgba(82, 136, 193, {alpha_bg:.3f});
                    border-radius: 20px;
                    border: 2px solid rgba(130, 190, 255, {alpha_border:.3f});
                }}
            """)
        else:
            base_color = QColor("#2b5278") if self.is_outgoing else QColor("#182533")
            glow_color = QColor("#4680b8")
            r = int(base_color.red() + (glow_color.red() - base_color.red()) * t)
            g = int(base_color.green() + (glow_color.green() - base_color.green()) * t)
            b = int(base_color.blue() + (glow_color.blue() - base_color.blue()) * t)
            border_alpha = t * 0.95
            corner = "border-bottom-right-radius: 3px;" if self.is_outgoing else "border-bottom-left-radius: 3px;"
            self.setStyleSheet(f"""
                QFrame#messageBubble {{
                    background-color: #{r:02x}{g:02x}{b:02x};
                    border-radius: 14px;
                    {corner}
                    border: 2px solid rgba(135, 195, 255, {border_alpha:.3f});
                }}
                QFrame#messageBubble:hover {{
                    background-color: #{r:02x}{g:02x}{b:02x};
                }}
            """)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.request_reply.emit(self.msg_data)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def set_read(self, is_read: bool):
        self.is_read = is_read
        self.msg_data["is_read"] = 1 if is_read else 0
        if self.tick_widget:
            self.tick_widget.set_read(is_read)

    def toggle_read_status(self):
        new_val = not self.is_read
        self.set_read(new_val)
        self.request_toggle_read_status.emit(self.db_id, new_val)

    def toggle_reaction(self, emoji: str):
        new_val = "" if self.reaction == emoji else emoji
        self.reaction = new_val
        self.msg_data["reactions"] = new_val
        self.request_reaction.emit(self.msg_data, new_val)

    def open_file(self, path: str):
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def show_context_menu(self, pos):
        menu = QMenu(self)

        # Reactions submenu
        rx_menu = menu.addMenu("✨ Tepki Bırak")
        for em, label in [("👍", "Beğen"), ("❤️", "Kalp"), ("🔥", "Alev"), ("😂", "Gülme"), ("👏", "Alkış"), ("😢", "Üzgün")]:
            act = rx_menu.addAction(f"{em}  {label}")
            act.triggered.connect(lambda _, e=em: self.toggle_reaction(e))
        menu.addSeparator()

        act_reply = QAction("↩️ Yanıtla", self)
        act_reply.triggered.connect(lambda: self.request_reply.emit(self.msg_data))
        menu.addAction(act_reply)

        if self.is_outgoing and self.msg_data.get("text"):
            act_edit = QAction("✏️ Düzenle", self)
            act_edit.triggered.connect(lambda: self.request_edit.emit(self.msg_data))
            menu.addAction(act_edit)

        if self.msg_data.get("text"):
            act_copy = QAction("📋 Metni Kopyala", self)
            act_copy.triggered.connect(self.copy_text)
            menu.addAction(act_copy)

        media_path = self.msg_data.get("media_path")
        if media_path and os.path.exists(media_path):
            menu.addSeparator()
            act_open = QAction("📂 Dosyayı Aç", self)
            act_open.triggered.connect(lambda: self.open_file(media_path))
            menu.addAction(act_open)

            act_del_file = QAction("🗑️ İndirilen Dosyayı Diskten Sil", self)
            act_del_file.triggered.connect(lambda: self.request_delete_media_file.emit(self.db_id))
            menu.addAction(act_del_file)
        menu.addSeparator()
        if not self.is_outgoing:
            is_del = bool(self.msg_data.get("is_deleted_by_sender"))
            tag_text = "↩️ 'Karşı Taraf Sildi' İşaretini Kaldır" if is_del else "⚠️ 'Karşı Taraf Sildi' Olarak İşaretle"
            act_tag_del = QAction(tag_text, self)
            act_tag_del.triggered.connect(lambda: self.request_toggle_deleted_by_sender.emit(self.msg_data))
            menu.addAction(act_tag_del)
        else:
            tag_read = "✓ Tek Tik (İletildi) Yap" if self.is_read else "✓✓ Çift Tik (Okundu) Yap"
            act_toggle_read = QAction(tag_read, self)
            act_toggle_read.triggered.connect(self.toggle_read_status)
            menu.addAction(act_toggle_read)

        act_del = QAction("🗑️ Sil...", self)
        act_del.triggered.connect(lambda: self.request_delete_dialog.emit(self.msg_data))
        menu.addAction(act_del)

        menu.exec(self.mapToGlobal(pos))

    def copy_text(self):
        text = self.msg_data.get("text", "")
        if text:
            QApplication.clipboard().setText(text)
            center_x = max(10, self.width() // 2 - 30)
            center_y = max(5, self.height() // 2 - 10)
            QToolTip.showText(self.mapToGlobal(QPoint(center_x, center_y)), "Metin Kopyalandı!", self)


class ChatItemWidget(QWidget):
    """Widget for chat item in list with Avatar, Pin, Custom Note, and badges."""
    def __init__(self, title: str, subtitle: str, is_pinned: bool = False,
                 custom_note: str = "", is_blocked: bool = False, unread_count: int = 0,
                 avatar_path: str = ""):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Avatar thumbnail (44x44)
        avatar_lbl = QLabel()
        avatar_lbl.setFixedSize(44, 44)
        avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if avatar_path and os.path.exists(avatar_path):
            avatar_lbl.setPixmap(make_circular_pixmap(QPixmap(avatar_path), 44))
        else:
            initial = title[0].upper() if title and title.strip() and title.strip() != "." else "?"
            avatar_lbl.setText(initial)
            avatar_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            bg_col = get_avatar_color(title)
            avatar_lbl.setStyleSheet(f"""
                background-color: {bg_col};
                color: white;
                border-radius: 22px;
            """)
        layout.addWidget(avatar_lbl)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)

        if is_pinned:
            pin_icon = QLabel("📌")
            pin_icon.setStyleSheet("font-size: 11px;")
            title_row.addWidget(pin_icon)

        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #ffffff;")
        title_label.setToolTip("Sohbeti açmak için tıklayın")
        title_row.addWidget(title_label)

        if custom_note:
            note_badge = QLabel(f"[{custom_note}]")
            note_badge.setFont(QFont("Segoe UI", 8))
            note_badge.setStyleSheet("color: #e5a93c; font-style: italic;")
            note_badge.setToolTip(f"Özel Not: {custom_note}")
            title_row.addWidget(note_badge)

        title_row.addStretch()
        text_layout.addLayout(title_row)

        sub_label = QLabel(subtitle)
        sub_label.setFont(QFont("Segoe UI", 9))
        sub_label.setStyleSheet("color: #7f91a4;")
        text_layout.addWidget(sub_label)

        layout.addLayout(text_layout, 1)

        if is_blocked:
            block_badge = QLabel("ENGEL")
            block_badge.setToolTip("Bu kullanıcı engellenmiş durumda")
            block_badge.setStyleSheet("""
                background-color: rgba(235, 87, 87, 0.2);
                color: #ff6b6b;
                border: 1px solid rgba(235, 87, 87, 0.4);
                border-radius: 6px;
                padding: 1px 6px;
                font-size: 10px;
                font-weight: bold;
            """)
            layout.addWidget(block_badge)

        if unread_count > 0:
            badge = QLabel(str(unread_count))
            badge.setMinimumWidth(20)
            badge.setFixedHeight(20)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setToolTip(f"{unread_count} okunmamış mesaj")
            badge.setStyleSheet("background-color: #5288c1; color: white; border-radius: 10px; font-weight: bold; font-size: 11px; padding: 0 4px;")
            layout.addWidget(badge)


class ChatInputEdit(QTextEdit):
    send_requested = pyqtSignal()
    image_pasted = pyqtSignal(str)
    cancel_action_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setPlaceholderText("Mesajınızı yazın... (Enter: Gönder, Shift+Enter: Yeni Satır, Ctrl+V: Resim)")
        self.setToolTip("Mesaj yazma alanı (Enter: Gönder, Shift+Enter: Yeni Satır, Ctrl+V: Resim Yapıştır)")
        self.setFixedHeight(46)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_action_requested.emit()
            return

        if event.matches(QKeySequence.StandardKey.Paste) or (event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            clipboard = QApplication.clipboard()
            mime = clipboard.mimeData()
            if mime.hasImage():
                image = clipboard.image()
                if not image.isNull():
                    temp_img_path = TEMP_DIR / f"pasted_{int(time.time()*1000)}.png"
                    image.save(str(temp_img_path), "PNG")
                    self.image_pasted.emit(str(temp_img_path.resolve()))
                    return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.send_requested.emit()
        else:
            super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, net_manager=None, db_manager=None):
        super().__init__()
        self.setWindowTitle("Anonim Telegram")
        self.resize(1180, 760)
        self.setMinimumSize(880, 600)
        self.setAcceptDrops(True)

        self.db = db_manager if db_manager else DatabaseManager()
        self.net_manager = net_manager if net_manager else NetworkShieldManager(mode=ShieldMode.DIRECT, is_frozen=False)
        # Load and apply persisted jitter timing configuration
        try:
            jitter_en = self.db.get_setting("jitter_enabled", "1") == "1"
            jitter_min = int(self.db.get_setting("jitter_min_ms", "350"))
            jitter_max = int(self.db.get_setting("jitter_max_ms", "1800"))
            self.net_manager.set_jitter(jitter_en, jitter_min, jitter_max)
        except Exception:
            pass
        self.spam_protector = SpamProtector(enabled=True)
        self.bot_manager = BotManager(spam_protector=self.spam_protector, db_manager=self.db, network_manager=self.net_manager)

        self.current_bot_id = None
        self.active_chat_id = None
        self.active_chat_name = ""
        self.selected_file_path = None
        self.active_reply_msg = None
        self.active_edit_msg = None
        self.unread_counts = {}
        self.chat_search_matches = []
        self.current_search_idx = -1
        self.last_typing_sent_time = 0
        self.stealth_typing = False
        self.emoji_picker = None
        self.rendered_message_bubbles = []
        self.panic_hotkey = self.db.get_setting("panic_hotkey", "Ctrl+Alt+Shift+X")

        self.connect_bot_signals()
        self.init_ui()
        self.apply_theme()
        self.show_no_chat_selected_state()
        self.load_initial_bots()
        self.update_network_shield_button()

    def connect_bot_signals(self):
        self.bot_manager.message_received.connect(self.on_message_received)
        self.bot_manager.message_sent.connect(self.on_message_sent)
        self.bot_manager.message_edited.connect(self.on_message_edited)
        self.bot_manager.message_edited_by_remote.connect(self.on_message_edited_by_remote)
        self.bot_manager.message_deleted.connect(self.on_message_deleted)
        self.bot_manager.profile_fetched.connect(self.on_user_profile_fetched)
        self.bot_manager.status_changed.connect(self.on_bot_status_changed)
        self.bot_manager.spam_detected.connect(self.on_spam_detected)
        self.bot_manager.message_reaction_received.connect(self.on_message_reaction_received)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Bar
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(50)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(14, 8, 14, 8)
        top_layout.setSpacing(10)

        brand_icon = QLabel("✈️")
        brand_icon.setFont(QFont("Segoe UI Emoji", 13))
        top_layout.addWidget(brand_icon)

        brand_title = QLabel("Anonim Telegram")
        brand_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        brand_title.setStyleSheet("color: #ffffff; margin-right: 4px;")
        top_layout.addWidget(brand_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #242f3d; margin: 4px 4px;")
        top_layout.addWidget(sep)

        bot_lbl = QLabel("Bot:")
        bot_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        bot_lbl.setStyleSheet("color: #7f91a4;")
        top_layout.addWidget(bot_lbl)

        self.bot_selector = QComboBox()
        self.bot_selector.setMinimumWidth(210)
        self.bot_selector.setFixedHeight(32)
        self.bot_selector.setToolTip("Yönetmek istediğiniz aktif Telegram botunu seçin")
        self.bot_selector.currentIndexChanged.connect(self.on_bot_selection_changed)
        top_layout.addWidget(self.bot_selector)

        self.btn_manage_bots = QPushButton("⚙️ Bot Yönetimi")
        self.btn_manage_bots.setFixedHeight(32)
        self.btn_manage_bots.setToolTip("Telegram botlarını ekle, düzenle veya kaldır")
        self.btn_manage_bots.clicked.connect(self.open_bot_manage_dialog)
        top_layout.addWidget(self.btn_manage_bots)

        self.btn_toggle_spam = QPushButton("🛡️ Spam Koruması: AÇIK")
        self.btn_toggle_spam.setFixedHeight(32)
        self.btn_toggle_spam.setToolTip("Otomatik spam ve flood korumasını aç / kapat")
        self.btn_toggle_spam.setStyleSheet("background-color: rgba(76, 217, 100, 0.14); color: #4cd964; border: 1px solid rgba(76, 217, 100, 0.35); border-radius: 16px; font-weight: 600; padding: 4px 14px; font-size: 12px;")
        self.btn_toggle_spam.clicked.connect(self.toggle_spam_protection)
        top_layout.addWidget(self.btn_toggle_spam)

        self.btn_stealth_mode = QPushButton("💬 Yazıyor: Açık")
        self.btn_stealth_mode.setFixedHeight(32)
        self.btn_stealth_mode.setToolTip("Gizlilik Modu: Karşı tarafa 'yazıyor...' bildirimi gönderimini aç / kapat")
        self.btn_stealth_mode.clicked.connect(self.toggle_stealth_typing)
        top_layout.addWidget(self.btn_stealth_mode)

        self.btn_network_shield = QPushButton("🛡️ Kalkan: Hazırlanıyor...")
        self.btn_network_shield.setFixedHeight(32)
        self.btn_network_shield.setToolTip("Ağ Güvenlik Kalkanı, Tor ve Proxy ayarlarını aç")
        self.btn_network_shield.clicked.connect(self.open_network_shield_settings)
        top_layout.addWidget(self.btn_network_shield)

        self.btn_panic_destruct = QPushButton("🚨 Acil İmha")
        self.btn_panic_destruct.setFixedHeight(32)
        self.btn_panic_destruct.setToolTip(f"Adli Bilişim Kurtarılamaz Acil İmha (Kısayol: {self.panic_hotkey} | Sağ tık: Kısayolu değiştir)")
        self.btn_panic_destruct.setStyleSheet("""
            QPushButton {
                background-color: rgba(235, 87, 87, 0.15);
                color: #ff6b6b;
                border: 1px solid rgba(235, 87, 87, 0.4);
                border-radius: 16px;
                font-weight: 600;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
                color: #ffffff;
            }
        """)
        self.btn_panic_destruct.clicked.connect(self.trigger_emergency_self_destruct)
        self.btn_panic_destruct.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_panic_destruct.customContextMenuRequested.connect(self.show_panic_button_menu)
        top_layout.addWidget(self.btn_panic_destruct)

        top_layout.addStretch()

        self.status_badge = QLabel("Bağlı Değil")
        self.status_badge.setObjectName("statusBadgeOffline")
        self.status_badge.setToolTip("Aktif botun Telegram API bağlantı durumu")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_badge.setFixedHeight(28)
        self.status_badge.setMinimumWidth(130)
        top_layout.addWidget(self.status_badge)

        main_layout.addWidget(top_bar)

        # 2. Main Content Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel (Chat List)
        left_widget = QWidget()
        left_widget.setObjectName("leftPanel")
        left_widget.setMinimumWidth(280)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchChatsInput")
        self.search_input.setFixedHeight(36)
        self.search_input.setPlaceholderText("Sohbetlerde ara (İsim, @kullanıcı veya ID)...")
        self.search_input.setToolTip("Sohbetleri isim, @kullanıcı adı, not veya ID ile filtreleyin (Kısayol: Ctrl+K)")
        self.search_input.textChanged.connect(self.filter_chats)
        left_layout.addWidget(self.search_input)

        self.chat_list_widget = QListWidget()
        self.chat_list_widget.setObjectName("chatList")
        self.chat_list_widget.itemClicked.connect(self.on_chat_selected)
        self.chat_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_list_widget.customContextMenuRequested.connect(self.show_chat_context_menu)
        left_layout.addWidget(self.chat_list_widget)

        # Empty Search / Empty Chats State Frame
        self.left_empty_frame = QFrame()
        self.left_empty_frame.setObjectName("leftEmptyFrame")
        left_empty_layout = QVBoxLayout(self.left_empty_frame)
        left_empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_empty_layout.setContentsMargins(10, 20, 10, 20)
        left_empty_layout.setSpacing(8)

        self.left_empty_icon = QLabel("🔍")
        self.left_empty_icon.setFont(QFont("Segoe UI", 20))
        self.left_empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_empty_layout.addWidget(self.left_empty_icon)

        self.left_empty_label = QLabel("Aramanızla eşleşen sohbet bulunamadı.")
        self.left_empty_label.setFont(QFont("Segoe UI", 9))
        self.left_empty_label.setStyleSheet("color: #9bb7d4;")
        self.left_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.left_empty_label.setWordWrap(True)
        left_empty_layout.addWidget(self.left_empty_label)

        self.left_empty_frame.setVisible(False)
        left_layout.addWidget(self.left_empty_frame)

        splitter.addWidget(left_widget)

        # Right Panel (Conversation)
        right_widget = QWidget()
        right_widget.setObjectName("rightPanel")
        right_widget.setMinimumWidth(440)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Chat Header (Advanced User Info Bar)
        self.chat_header = QFrame()
        self.chat_header.setObjectName("chatHeader")
        header_layout = QHBoxLayout(self.chat_header)
        header_layout.setContentsMargins(16, 9, 16, 9)
        header_layout.setSpacing(12)

        # User Avatar Circle
        self.avatar_label = QLabel("?")
        self.avatar_label.setFixedSize(44, 44)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.avatar_label.setToolTip("Profili ve paylaşılan medyaları görüntüle")
        self.avatar_label.setCursor(Qt.CursorShape.PointingHandCursor)
        make_clickable(self.avatar_label, self.open_user_profile_dialog)
        self.avatar_label.setStyleSheet("""
            background-color: #5288c1;
            color: white;
            border-radius: 22px;
        """)
        header_layout.addWidget(self.avatar_label, 0, Qt.AlignmentFlag.AlignVCenter)

        # User details vertical
        user_info_box = QVBoxLayout()
        user_info_box.setContentsMargins(0, 0, 0, 0)
        user_info_box.setSpacing(2)

        # Top line: Title + Note Badge + ID Badge
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        self.chat_title = QLabel("Bir sohbet seçin")
        self.chat_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.chat_title.setStyleSheet("color: #ffffff;")
        self.chat_title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chat_title.setToolTip("Profili ve paylaşılan medyaları görüntüle")
        make_clickable(self.chat_title, self.open_user_profile_dialog)
        title_row.addWidget(self.chat_title)

        self.note_label = QLabel("")
        self.note_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.note_label.setStyleSheet("""
            QLabel {
                background-color: rgba(229, 169, 60, 0.15);
                color: #f5b041;
                border: 1px solid rgba(229, 169, 60, 0.35);
                border-radius: 6px;
                padding: 1px 7px;
            }
        """)
        self.note_label.setVisible(False)
        title_row.addWidget(self.note_label)

        self.id_badge_btn = QPushButton("ID: -")
        self.id_badge_btn.setToolTip("ID'yi kopyalamak için tıklayın")
        self.id_badge_btn.setFixedHeight(22)
        self.id_badge_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(82, 136, 193, 0.12);
                color: #649ad4;
                border: 1px solid rgba(82, 136, 193, 0.28);
                border-radius: 6px;
                padding: 1px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #5288c1; color: white; }
        """)
        self.id_badge_btn.clicked.connect(self.copy_active_chat_id)
        self.id_badge_btn.setVisible(False)
        title_row.addWidget(self.id_badge_btn)

        title_row.addStretch(1)

        # Bottom line: Username + Status
        sub_info_layout = QHBoxLayout()
        sub_info_layout.setContentsMargins(0, 0, 0, 0)
        sub_info_layout.setSpacing(8)

        self.chat_uname_label = QLabel("")
        self.chat_uname_label.setFont(QFont("Segoe UI", 9))
        self.chat_uname_label.setStyleSheet("color: #649ad4; font-weight: 500;")
        self.chat_uname_label.setVisible(False)
        sub_info_layout.addWidget(self.chat_uname_label)

        self.chat_status_label = QLabel("")
        self.chat_status_label.setFont(QFont("Segoe UI", 8))
        self.chat_status_label.setStyleSheet("color: #7f91a4;")
        sub_info_layout.addWidget(self.chat_status_label)

        sub_info_layout.addStretch(1)

        user_info_box.addLayout(title_row)
        user_info_box.addLayout(sub_info_layout)
        header_layout.addLayout(user_info_box, 1)

        # Action Buttons in Header
        header_buttons_layout = QHBoxLayout()
        header_buttons_layout.setContentsMargins(0, 0, 0, 0)
        header_buttons_layout.setSpacing(6)

        self.btn_profile = QPushButton("👤 Profil")
        self.btn_profile.setFixedHeight(30)
        self.btn_profile.setToolTip("Kullanıcı Profili ve Paylaşılan Medyalar")
        self.btn_profile.clicked.connect(self.open_user_profile_dialog)
        self.btn_profile.setVisible(False)
        header_buttons_layout.addWidget(self.btn_profile)

        self.btn_search_chat = QPushButton("🔍 Ara")
        self.btn_search_chat.setFixedHeight(30)
        self.btn_search_chat.setToolTip("Sohbette Ara (Ctrl+F)")
        self.btn_search_chat.clicked.connect(self.toggle_chat_search)
        self.btn_search_chat.setVisible(False)
        header_buttons_layout.addWidget(self.btn_search_chat)

        self.btn_pin = QPushButton("📌 Sabitle")
        self.btn_pin.setFixedHeight(30)
        self.btn_pin.setToolTip("Bu sohbeti listenin en üstüne sabitle / sabitlemeyi kaldır")
        self.btn_pin.clicked.connect(self.toggle_active_chat_pin)
        self.btn_pin.setVisible(False)
        header_buttons_layout.addWidget(self.btn_pin)

        self.btn_add_note = QPushButton("📝 Not")
        self.btn_add_note.setFixedHeight(30)
        self.btn_add_note.setToolTip("Bu kullanıcı için özel not veya takma ad belirle")
        self.btn_add_note.clicked.connect(self.edit_active_chat_note)
        self.btn_add_note.setVisible(False)
        header_buttons_layout.addWidget(self.btn_add_note)

        self.btn_export = QPushButton("💾 Dışa Aktar")
        self.btn_export.setFixedHeight(30)
        self.btn_export.setToolTip("Sohbet geçmişini metin dosyası (.txt) olarak kaydet")
        self.btn_export.clicked.connect(self.export_active_chat)
        self.btn_export.setVisible(False)
        header_buttons_layout.addWidget(self.btn_export)

        self.btn_block_toggle = QPushButton("Engelle")
        self.btn_block_toggle.setFixedHeight(30)
        self.btn_block_toggle.setToolTip("Bu kullanıcının bota mesaj göndermesini engelle veya engeli kaldır")
        self.btn_block_toggle.setVisible(False)
        self.btn_block_toggle.clicked.connect(self.toggle_active_chat_block)
        header_buttons_layout.addWidget(self.btn_block_toggle)

        header_layout.addLayout(header_buttons_layout, 0)

        right_layout.addWidget(self.chat_header)

        # In-Chat Search Bar
        self.chat_search_bar = QFrame()
        self.chat_search_bar.setStyleSheet("""
            QFrame {
                background-color: #17212b;
                border-bottom: 1px solid #242f3d;
                padding: 3px;
            }
        """)
        search_layout = QHBoxLayout(self.chat_search_bar)
        search_layout.setContentsMargins(15, 6, 15, 6)
        search_layout.setSpacing(8)

        search_icon = QLabel("🔍")
        search_layout.addWidget(search_icon)

        self.chat_search_input = QLineEdit()
        self.chat_search_input.setPlaceholderText("Bu sohbette mesaj ara... (Enter: Sonraki, Shift+Enter: Önceki)")
        self.chat_search_input.setToolTip("Sohbet içinde arama terimi girin (Enter: Sonraki, Shift+Enter: Önceki, Esc: Kapat)")
        self.chat_search_input.textChanged.connect(self.perform_chat_search)
        self.chat_search_input.returnPressed.connect(self.next_search_match)
        search_layout.addWidget(self.chat_search_input, 1)

        self.chat_search_count_lbl = QLabel("0 / 0")
        self.chat_search_count_lbl.setStyleSheet("color: #9bb7d4; font-size: 11px;")
        search_layout.addWidget(self.chat_search_count_lbl)

        btn_prev_search = QPushButton("▲")
        btn_prev_search.setFixedSize(28, 28)
        btn_prev_search.setToolTip("Önceki Eşleşme (Shift+Enter)")
        btn_prev_search.setStyleSheet("""
            QPushButton {
                background-color: #242f3d;
                color: #d1dbe5;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #2b5278; color: white; border-color: #5288c1; }
        """)
        btn_prev_search.clicked.connect(self.prev_search_match)
        search_layout.addWidget(btn_prev_search)

        btn_next_search = QPushButton("▼")
        btn_next_search.setFixedSize(28, 28)
        btn_next_search.setToolTip("Sonraki Eşleşme (Enter)")
        btn_next_search.setStyleSheet("""
            QPushButton {
                background-color: #242f3d;
                color: #d1dbe5;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #2b5278; color: white; border-color: #5288c1; }
        """)
        btn_next_search.clicked.connect(self.next_search_match)
        search_layout.addWidget(btn_next_search)

        btn_close_search = QPushButton("✕")
        btn_close_search.setFixedSize(28, 28)
        btn_close_search.setToolTip("Aramayı Kapat (Esc)")
        btn_close_search.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #7f91a4;
                border: none;
                border-radius: 14px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #242f3d; color: white; }
        """)
        btn_close_search.clicked.connect(self.close_chat_search)
        search_layout.addWidget(btn_close_search)

        self.chat_search_bar.setVisible(False)
        right_layout.addWidget(self.chat_search_bar)

        # In-Chat Search Shortcuts
        shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut_search.activated.connect(self.toggle_chat_search)

        # Network Freeze Lock Banner (IP Leak Protection during proxy/tunnel changes)
        self.network_freeze_banner = QFrame()
        self.network_freeze_banner.setFixedHeight(36)
        self.network_freeze_banner.setStyleSheet("""
            QFrame {
                background-color: rgba(226, 83, 99, 0.18);
                border: 1px solid rgba(226, 83, 99, 0.45);
                border-radius: 8px;
                margin: 4px 12px;
            }
        """)
        freeze_b_layout = QHBoxLayout(self.network_freeze_banner)
        freeze_b_layout.setContentsMargins(10, 4, 10, 4)
        self.network_freeze_banner_label = QLabel("🔒 AĞ TRAFİĞİ DONDURULDU: IP sızıntı koruması devrede. Yeni bağlantı kuruluyor...")
        self.network_freeze_banner_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.network_freeze_banner_label.setStyleSheet("color: #ff6b7a;")
        freeze_b_layout.addWidget(self.network_freeze_banner_label)
        self.network_freeze_banner.setVisible(False)
        right_layout.addWidget(self.network_freeze_banner)

        # Messages Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("messageArea")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.messages_container = ChatWallpaperWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(16, 10, 16, 10)
        self.messages_layout.setSpacing(4)
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_container)
        right_layout.addWidget(self.scroll_area, 1)

        # Action Bar (Reply / Edit Preview)
        self.action_preview_bar = QFrame()
        self.action_preview_bar.setStyleSheet("""
            QFrame {
                background-color: #17212b;
                border-top: 1px solid #101921;
                border-left: 3px solid #5288c1;
            }
        """)
        act_layout = QHBoxLayout(self.action_preview_bar)
        act_layout.setContentsMargins(12, 6, 12, 6)

        self.action_icon_label = QLabel("↩️")
        self.action_text_label = QLabel("")
        self.action_text_label.setStyleSheet("color: #9bb7d4; font-size: 12px;")

        btn_cancel_action = QPushButton("✕")
        btn_cancel_action.setToolTip("Yanıtlamayı veya Düzenlemeyi İptal Et (Esc)")
        btn_cancel_action.setFixedSize(24, 24)
        btn_cancel_action.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #7f91a4;
                border: none;
                border-radius: 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #242f3d; color: white; }
        """)
        btn_cancel_action.clicked.connect(self.cancel_active_action)

        act_layout.addWidget(self.action_icon_label)
        act_layout.addWidget(self.action_text_label, 1)
        act_layout.addWidget(btn_cancel_action)
        self.action_preview_bar.setVisible(False)
        right_layout.addWidget(self.action_preview_bar)

        # Attachment Bar
        self.attachment_bar = QFrame()
        self.attachment_bar.setStyleSheet("background-color: #17212b; border-top: 1px solid #101921; padding: 4px;")
        att_layout = QHBoxLayout(self.attachment_bar)
        att_layout.setContentsMargins(15, 6, 15, 6)
        self.att_thumb_label = QLabel()
        self.att_thumb_label.setFixedSize(36, 36)
        self.attachment_label = QLabel("📎 Ek: -")
        self.attachment_label.setStyleSheet("color: #5288c1; font-weight: bold;")
        btn_cancel_att = QPushButton("✕")
        btn_cancel_att.setToolTip("Dosya ekini kaldır")
        btn_cancel_att.setFixedSize(24, 24)
        btn_cancel_att.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #7f91a4;
                border: none;
                border-radius: 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #242f3d; color: white; }
        """)
        btn_cancel_att.clicked.connect(self.cancel_attachment)

        att_layout.addWidget(self.att_thumb_label)
        att_layout.addWidget(self.attachment_label)
        att_layout.addStretch()
        att_layout.addWidget(btn_cancel_att)
        self.attachment_bar.setVisible(False)
        right_layout.addWidget(self.attachment_bar)

        # Input Frame
        input_frame = QFrame()
        input_frame.setObjectName("inputFrame")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)
        input_layout.setSpacing(8)

        self.btn_attach = QPushButton("📎")
        self.btn_attach.setObjectName("btnAttach")
        self.btn_attach.setToolTip("Dosya veya Görsel Ekle (Kısayol: Ctrl+O veya sürükleyip bırak)")
        self.btn_attach.setFixedSize(38, 38)
        self.btn_attach.setFont(QFont("Segoe UI", 12))
        self.btn_attach.clicked.connect(self.select_file_attachment)
        input_layout.addWidget(self.btn_attach)

        self.btn_quick = QPushButton("⚡")
        self.btn_quick.setObjectName("btnQuick")
        self.btn_quick.setToolTip("Hızlı Yanıt Şablonları (Hazır kalıpları hızlıca gönder)")
        self.btn_quick.setFixedSize(38, 38)
        self.btn_quick.setFont(QFont("Segoe UI", 12))
        self.btn_quick.clicked.connect(self.show_quick_replies_menu)
        input_layout.addWidget(self.btn_quick)

        self.msg_input = ChatInputEdit()
        self.msg_input.setObjectName("msgInput")
        self.msg_input.send_requested.connect(self.send_or_save_message)
        self.msg_input.image_pasted.connect(self.handle_pasted_image)
        self.msg_input.cancel_action_requested.connect(self.cancel_active_action)
        self.msg_input.textChanged.connect(self.on_input_text_changed)
        input_layout.addWidget(self.msg_input, 1)

        self.btn_neutralize = QPushButton("🪄")
        self.btn_neutralize.setObjectName("btnNeutralize")
        self.btn_neutralize.setToolTip("Yazı Stilini ve Kimlik İfadelerini Nötrleştir (Kısayol: Ctrl+Shift+N)")
        self.btn_neutralize.setFixedSize(38, 38)
        self.btn_neutralize.setFont(QFont("Segoe UI Emoji", 13))
        self.btn_neutralize.clicked.connect(self.neutralize_input_text)
        input_layout.addWidget(self.btn_neutralize)

        self.btn_emoji = QPushButton("😊")
        self.btn_emoji.setObjectName("btnEmoji")
        self.btn_emoji.setToolTip("Emoji Seçici (Kısayol: Ctrl+E)")
        self.btn_emoji.setFixedSize(38, 38)
        self.btn_emoji.setFont(QFont("Segoe UI Emoji", 14))
        self.btn_emoji.clicked.connect(self.toggle_emoji_picker)
        input_layout.addWidget(self.btn_emoji)

        self.btn_send = QPushButton("Gönder")
        self.btn_send.setObjectName("btnSend")
        self.btn_send.setToolTip("Mesajı Gönder (Enter)")
        self.btn_send.setFixedHeight(38)
        self.btn_send.setMinimumWidth(82)
        self.btn_send.clicked.connect(self.send_or_save_message)
        input_layout.addWidget(self.btn_send)

        right_layout.addWidget(input_frame)

        splitter.addWidget(right_widget)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)
        main_layout.addWidget(splitter, 1)

        # Global Productivity Shortcuts
        shortcut_search_chats = QShortcut(QKeySequence("Ctrl+K"), self)
        shortcut_search_chats.activated.connect(lambda: (self.search_input.setFocus(), self.search_input.selectAll()))

        shortcut_emoji = QShortcut(QKeySequence("Ctrl+E"), self)
        shortcut_emoji.activated.connect(self.toggle_emoji_picker)

        shortcut_attach = QShortcut(QKeySequence("Ctrl+O"), self)
        shortcut_attach.activated.connect(self.select_file_attachment)

        shortcut_neutralize = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
        shortcut_neutralize.activated.connect(self.neutralize_input_text)

        # Global emergency self-destruct shortcut
        self.panic_shortcut = QShortcut(QKeySequence(self.panic_hotkey), self)
        self.panic_shortcut.activated.connect(self.trigger_emergency_self_destruct)

    def neutralize_input_text(self):
        txt = self.msg_input.toPlainText()
        if not txt:
            return
        try:
            from text_neutralizer import TextNeutralizer
            neutral = TextNeutralizer.neutralize(txt)
            self.msg_input.setPlainText(neutral)
            QToolTip.showText(self.btn_neutralize.mapToGlobal(QPoint(0, -32)), "🪄 Yazı stili ve kimlik ifadeleri nötrleştirildi!", self.btn_neutralize)
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"Nötrleştirme hatası: {str(e)}")

    def show_panic_button_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #17212b; color: #ffffff; border: 1px solid #242f3d; } QMenu::item:selected { background-color: #2b5278; }")
        act_change = QAction(f"⌨️ Kısayol Kombinasyonunu Değiştir (Mevcut: {self.panic_hotkey})", self)
        act_change.triggered.connect(self.change_panic_hotkey)
        menu.addAction(act_change)
        act_trigger = QAction("🚨 Şimdi Acil İmha Et...", self)
        act_trigger.triggered.connect(self.trigger_emergency_self_destruct)
        menu.addAction(act_trigger)
        menu.exec(self.btn_panic_destruct.mapToGlobal(pos))

    def change_panic_hotkey(self):
        new_key, ok = QInputDialog.getText(
            self, "Acil İmha Kısayolu",
            "Yeni acil imha tuş kombinasyonunu girin (örn. Ctrl+Alt+Shift+X, Ctrl+Shift+Delete):",
            text=self.panic_hotkey
        )
        if ok and new_key.strip():
            self.panic_hotkey = new_key.strip()
            self.db.set_setting("panic_hotkey", self.panic_hotkey)
            self.panic_shortcut.setKey(QKeySequence(self.panic_hotkey))
            self.btn_panic_destruct.setToolTip(f"Adli Bilişim Kurtarılamaz Acil İmha (Kısayol: {self.panic_hotkey} | Sağ tık: Kısayolu değiştir)")
            QMessageBox.information(self, "Bilgi", f"Acil durum imha kısayolu '{self.panic_hotkey}' olarak kaydedildi.")

    def trigger_emergency_self_destruct(self):
        dlg = EmergencyDestructDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            execute_emergency_self_destruct(workspace_dir=Path.cwd(), app_pid=os.getpid())

    # --- DRAG & DROP ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if os.path.exists(file_path):
                self.set_file_attachment(file_path)

    def handle_pasted_image(self, img_path: str):
        self.set_file_attachment(img_path)

    def select_file_attachment(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Gönderilecek Dosyayı Seçin", "", "Tüm Dosyalar (*.*)")
        if file_path:
            self.set_file_attachment(file_path)

    def set_file_attachment(self, file_path: str):
        is_img = file_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))
        if is_img:
            dlg = ImageSecurityDialog(file_path, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

        self.selected_file_path = file_path
        f_name = Path(file_path).name
        clean_hint = " (🛡️ EXIF/Konum Temizlendi)" if is_img else ""
        self.attachment_label.setText(f"📎 Gönderilecek Dosya: {f_name}{clean_hint}")

        pix = QPixmap(file_path)
        if not pix.isNull():
            self.att_thumb_label.setPixmap(pix.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.att_thumb_label.setVisible(True)
        else:
            self.att_thumb_label.setVisible(False)

        self.attachment_bar.setVisible(True)
        self.msg_input.setFocus()

    def cancel_attachment(self):
        self.selected_file_path = None
        self.attachment_bar.setVisible(False)

    def cancel_active_action(self):
        self.active_reply_msg = None
        self.active_edit_msg = None
        self.action_preview_bar.setVisible(False)
        self.btn_send.setText("Gönder")

    # --- HIZLI YANITLAR (CANNED RESPONSES) ---
    def show_quick_replies_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #17212b; color: #ffffff; border: 1px solid #242f3d; } QMenu::item:selected { background-color: #2b5278; }")
        replies = self.db.get_quick_replies()

        for item in replies:
            title = item.get("title") or "Şablon"
            text = item.get("text") or ""
            act = QAction(f"⚡ {title}: {text[:35]}...", self)
            act.triggered.connect(lambda chk, t=text: self.insert_quick_reply(t))
            menu.addAction(act)

        menu.addSeparator()
        act_add = QAction("+ Yeni Şablon Ekle...", self)
        act_add.triggered.connect(self.add_new_quick_reply_prompt)
        menu.addAction(act_add)

        btn_pos = self.btn_quick.mapToGlobal(QPoint(0, -menu.sizeHint().height()))
        menu.exec(btn_pos)

    def insert_quick_reply(self, text: str):
        self.msg_input.setPlainText(text)
        self.msg_input.setFocus()

    def add_new_quick_reply_prompt(self):
        title, ok1 = QInputDialog.getText(self, "Yeni Şablon", "Şablon Başlığı (örn: İndirim):")
        if not ok1 or not title.strip():
            return
        text, ok2 = QInputDialog.getMultiLineText(self, "Yeni Şablon", "Mesaj Metni:")
        if ok2 and text.strip():
            self.db.add_quick_reply(title.strip(), text.strip())
            QMessageBox.information(self, "Başarılı", "Hızlı yanıt şablonu kaydedildi!")

    # --- SOHBET İÇİ ARAMA (IN-CHAT SEARCH) ---
    def toggle_chat_search(self):
        if not self.active_chat_id:
            return
        is_visible = self.chat_search_bar.isVisible()
        if is_visible:
            self.close_chat_search()
        else:
            self.chat_search_bar.setVisible(True)
            self.chat_search_input.setFocus()
            self.chat_search_input.selectAll()
            if self.chat_search_input.text().strip():
                self.perform_chat_search()

    def close_chat_search(self):
        self.chat_search_bar.setVisible(False)
        self.clear_search_highlights()
        self.chat_search_matches = []
        self.current_search_idx = -1
        self.chat_search_count_lbl.setText("0 / 0")

    def perform_chat_search(self):
        query = self.chat_search_input.text().strip().lower()
        self.clear_search_highlights()
        self.chat_search_matches = []
        self.current_search_idx = -1

        if not query:
            self.chat_search_count_lbl.setText("0 / 0")
            self.chat_search_count_lbl.setStyleSheet("color: #9bb7d4; font-size: 11px;")
            return

        for i in range(self.messages_layout.count() - 1):
            row_item = self.messages_layout.itemAt(i)
            if not row_item or not row_item.widget():
                continue
            row_widget = row_item.widget()
            bubbles = row_widget.findChildren(MessageBubbleWidget)
            for bubble in bubbles:
                text = (bubble.msg_data.get("text") or "").lower()
                fname = (bubble.msg_data.get("file_name") or "").lower()
                if query in text or query in fname:
                    self.chat_search_matches.append(bubble)

        total = len(self.chat_search_matches)
        if total > 0:
            self.current_search_idx = total - 1
            self.chat_search_count_lbl.setStyleSheet("color: #9bb7d4; font-size: 11px; font-weight: bold;")
            self.update_search_match_display()
        else:
            self.chat_search_count_lbl.setText("Sonuç yok")
            self.chat_search_count_lbl.setStyleSheet("color: #ff7b88; font-size: 11px; font-weight: bold;")

    def update_search_match_display(self):
        total = len(self.chat_search_matches)
        if total == 0 or self.current_search_idx < 0:
            self.chat_search_count_lbl.setText("0 / 0")
            return

        self.chat_search_count_lbl.setText(f"{self.current_search_idx + 1} / {total}")

        for idx, bubble in enumerate(self.chat_search_matches):
            if idx == self.current_search_idx:
                bubble.setStyleSheet(self._get_bubble_style(bubble.is_outgoing) + " QFrame#messageBubble { border: 2px solid #e5a93c; }")
                self.scroll_area.ensureWidgetVisible(bubble)
            else:
                bubble.setStyleSheet(self._get_bubble_style(bubble.is_outgoing) + " QFrame#messageBubble { border: 1px solid #5288c1; }")

    def prev_search_match(self):
        if not self.chat_search_matches:
            return
        self.current_search_idx = (self.current_search_idx - 1) % len(self.chat_search_matches)
        self.update_search_match_display()

    def next_search_match(self):
        if not self.chat_search_matches:
            return
        self.current_search_idx = (self.current_search_idx + 1) % len(self.chat_search_matches)
        self.update_search_match_display()

    def clear_search_highlights(self):
        for bubble in self.chat_search_matches:
            bubble.setStyleSheet(self._get_bubble_style(bubble.is_outgoing))

    def _get_bubble_style(self, is_outgoing: bool) -> str:
        if is_outgoing:
            return """
                QFrame#messageBubble {
                    background-color: #2b5278;
                    border-radius: 12px;
                    border-bottom-right-radius: 3px;
                }
                QFrame#messageBubble:hover {
                    background-color: #315c86;
                }
                QLabel { color: #ffffff; }
            """
        else:
            return """
                QFrame#messageBubble {
                    background-color: #182533;
                    border-radius: 12px;
                    border-bottom-left-radius: 3px;
                }
                QFrame#messageBubble:hover {
                    background-color: #1d2d3d;
                }
                QLabel { color: #f5f5f5; }
            """

    # --- KULLANICI DETAY İŞLEMLERİ ---
    def copy_active_chat_id(self):
        if self.active_chat_id:
            QApplication.clipboard().setText(str(self.active_chat_id))
            QToolTip.showText(self.id_badge_btn.mapToGlobal(QPoint(0, 20)), "ID Kopyalandı!", self.id_badge_btn)

    def edit_active_chat_note(self):
        if not self.current_bot_id or not self.active_chat_id:
            return
        chats = self.db.get_chats_for_bot(self.current_bot_id)
        current_chat = next((c for c in chats if c["chat_id"] == self.active_chat_id), {})
        cur_note = current_chat.get("custom_note") or ""

        new_note, ok = QInputDialog.getText(self, "Özel Not Düzenle",
                                           f"'{self.active_chat_name}' kullanıcısı için özel not/takma ad:",
                                           text=cur_note)
        if ok:
            cleaned_note = new_note.strip()
            self.db.set_chat_note(self.current_bot_id, self.active_chat_id, cleaned_note)
            if cleaned_note:
                self.note_label.setText(f"📝 {cleaned_note}")
                self.note_label.setVisible(True)
            else:
                self.note_label.setText("")
                self.note_label.setVisible(False)
            self.refresh_chats()
            QToolTip.showText(self.btn_add_note.mapToGlobal(QPoint(0, 32)), "Not güncellendi!", self.btn_add_note)

    def toggle_active_chat_pin(self):
        if not self.current_bot_id or not self.active_chat_id:
            return
        chats = self.db.get_chats_for_bot(self.current_bot_id)
        current_chat = next((c for c in chats if c["chat_id"] == self.active_chat_id), {})
        is_pinned = bool(current_chat.get("is_pinned"))
        new_state = 0 if is_pinned else 1
        self.db.toggle_pin_chat(self.current_bot_id, self.active_chat_id, new_state)

        self.btn_pin.setText("📌 Sabitlendi" if new_state else "📌 Sabitle")
        self.btn_pin.setStyleSheet("background-color: #2b5278; color: #ffffff; border: 1px solid #5288c1; border-radius: 8px; font-weight: 600;" if new_state else "")
        tip_text = "Sohbet başa sabitlendi!" if new_state else "Sabitleme kaldırıldı!"
        QToolTip.showText(self.btn_pin.mapToGlobal(QPoint(0, 32)), tip_text, self.btn_pin)
        self.refresh_chats()

    def export_active_chat(self):
        if not self.current_bot_id or not self.active_chat_id:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Sohbeti Dışa Aktar",
            f"sohbet_{self.active_chat_id}_{datetime.now().strftime('%Y%m%d')}.txt",
            "Metin Dosyaları (*.txt)"
        )
        if not file_path:
            return

        messages = self.db.get_messages(self.current_bot_id, self.active_chat_id)
        lines = [
            f"=== SOHBET GEÇMİŞİ ===",
            f"Kullanıcı: {self.active_chat_name} (ID: {self.active_chat_id})",
            f"Dışa Aktarma Tarihi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 30 + "\n"
        ]
        for m in messages:
            sender = "BOT (Siz)" if m["is_outgoing"] else self.active_chat_name
            t_str = datetime.fromtimestamp(m["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            body = m["text"] or ""
            if m["media_type"]:
                body += f" [Dosya: {m['file_name'] or m['media_type']}]"
            lines.append(f"[{t_str}] {sender}: {body}")

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "Başarılı", f"Sohbet geçmişi kaydedildi:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Dışa aktarılamadı: {str(e)}")

    def toggle_emoji_picker(self):
        if self.emoji_picker is None:
            self.emoji_picker = EmojiPickerPopup(self)
            self.emoji_picker.emoji_selected.connect(self.insert_emoji)
        if self.emoji_picker.isVisible():
            self.emoji_picker.hide()
        else:
            btn_pos = self.btn_emoji.mapToGlobal(QPoint(0, 0))
            popup_x = max(10, btn_pos.x() - 150)
            popup_y = max(10, btn_pos.y() - 250)
            self.emoji_picker.move(popup_x, popup_y)
            self.emoji_picker.show()

    def insert_emoji(self, emoji_str: str):
        self.msg_input.insertPlainText(emoji_str)
        self.msg_input.setFocus()

    def on_input_text_changed(self):
        if not self.current_bot_id or not self.active_chat_id:
            return
        text = self.msg_input.toPlainText()
        if not text.strip():
            return
        now = time.time()
        if now - self.last_typing_sent_time > 4.0:
            self.last_typing_sent_time = now
            if getattr(self, "stealth_typing", False):
                return
            worker = self.bot_manager.get_worker(self.current_bot_id)
            if worker and worker.isRunning():
                worker.send_chat_action_async(self.active_chat_id, "typing")

    def update_chat_header_status(self, last_ts: int = None):
        if not self.active_chat_id or not self.current_bot_id:
            self.chat_status_label.setText("")
            return
        if not last_ts:
            messages = self.db.get_messages(self.current_bot_id, self.active_chat_id)
            incoming_ts = [m["timestamp"] for m in messages if not m.get("is_outgoing") and m.get("timestamp")]
            last_ts = max(incoming_ts) if incoming_ts else 0

        if not last_ts:
            chat = self.db.get_chat(self.current_bot_id, self.active_chat_id) or {}
            last_ts = chat.get("last_seen") or 0

        if not last_ts:
            self.chat_status_label.setText("son görülme bilinmiyor")
            self.chat_status_label.setStyleSheet("color: #7f91a4; font-size: 11px;")
            return

        now = int(time.time())
        diff = now - last_ts
        if diff < 300:
            self.chat_status_label.setText("🟢 çevrimiçi")
            self.chat_status_label.setStyleSheet("color: #4cd964; font-size: 11px; font-weight: bold;")
        else:
            dt = datetime.fromtimestamp(last_ts)
            today = datetime.now().date()
            if dt.date() == today:
                time_str = dt.strftime("%H:%M")
                self.chat_status_label.setText(f"son görülme bugün {time_str}")
            elif dt.date() == today - timedelta(days=1):
                time_str = dt.strftime("%H:%M")
                self.chat_status_label.setText(f"son görülme dün {time_str}")
            else:
                date_str = dt.strftime("%d.%m.%Y")
                self.chat_status_label.setText(f"son görülme {date_str}")
            self.chat_status_label.setStyleSheet("color: #7f91a4; font-size: 11px;")

    def on_reaction_requested(self, msg_data: dict, reaction: str):
        db_id = msg_data.get("id")
        if not db_id:
            return
        self.db.update_message_reaction(db_id, reaction)
        msg_data["reactions"] = reaction

        bot_id = msg_data.get("bot_id", self.current_bot_id)
        worker = self.bot_manager.get_worker(bot_id)
        if worker and worker.isRunning() and msg_data.get("message_id"):
            worker.send_reaction_async(msg_data["chat_id"], msg_data["message_id"], reaction)

        if self.active_chat_id:
            self.render_messages(self.active_chat_id)

    # --- MESAJ YANITLAMA & DÜZENLEME ---
    def on_reply_requested(self, msg_data: dict):
        self.active_edit_msg = None
        self.active_reply_msg = msg_data
        name = msg_data.get("sender_name") or ("Siz" if msg_data.get("is_outgoing") else "Kullanıcı")
        txt = msg_data.get("text") or "[Medya]"
        self.action_icon_label.setText("↩️")
        self.action_text_label.setText(f"<b>{name}</b> kullanıcısına yanıt veriliyor:<br>{txt[:50]}")
        self.action_preview_bar.setVisible(True)
        self.msg_input.setFocus()

    def on_edit_requested(self, msg_data: dict):
        self.active_reply_msg = None
        self.active_edit_msg = msg_data
        txt = msg_data.get("text", "")
        self.action_icon_label.setText("✏️")
        self.action_text_label.setText(f"<b>Mesaj düzenleniyor:</b> {txt[:50]}")
        self.action_preview_bar.setVisible(True)
        self.msg_input.setPlainText(txt)
        self.btn_send.setText("Kaydet")
        self.msg_input.setFocus()

    def send_or_save_message(self):
        if not self.current_bot_id or not self.active_chat_id:
            QToolTip.showText(self.btn_send.mapToGlobal(QPoint(0, -32)), "Lütfen önce bir sohbet seçin", self.btn_send)
            return

        worker = self.bot_manager.get_worker(self.current_bot_id)
        if not worker or not worker.isRunning():
            QMessageBox.warning(self, "Hata", "Seçili bot çalışmıyor!")
            return

        text = self.msg_input.toPlainText().strip()

        if self.active_edit_msg:
            if not text:
                QToolTip.showText(self.btn_send.mapToGlobal(QPoint(0, -32)), "Mesaj metni boş olamaz", self.btn_send)
                return
            msg_id = self.active_edit_msg.get("message_id")
            db_id = self.active_edit_msg.get("id")
            if msg_id:
                worker.edit_message_async(self.active_chat_id, msg_id, text)
            self.db.update_message_text(db_id, text)
            self.cancel_active_action()
            self.msg_input.clear()
            self.render_messages(self.active_chat_id)
            return

        file_to_send = self.selected_file_path
        if not text and not file_to_send:
            QToolTip.showText(self.btn_send.mapToGlobal(QPoint(0, -32)), "Lütfen bir mesaj yazın veya dosya ekleyin", self.btn_send)
            return

        reply_id = self.active_reply_msg.get("message_id") if self.active_reply_msg else None
        reply_preview = (self.active_reply_msg.get("text") or "[Medya]") if self.active_reply_msg else None

        self.msg_input.clear()
        self.cancel_attachment()
        self.cancel_active_action()

        if file_to_send:
            worker.send_file_async(self.active_chat_id, file_to_send, text, reply_id, reply_preview)
        else:
            worker.send_message_async(self.active_chat_id, text, reply_id, reply_preview)

    def on_message_edited(self, bot_id: int, chat_id: int, msg_id: int, new_text: str, success: bool, err: str):
        if not success:
            QMessageBox.warning(self, "Düzenleme Hatası", f"Telegram'daki mesaj düzenlenemedi:\n{err}")

    # --- TELEGRAM DELETE MODAL ---
    def on_delete_dialog_requested(self, msg_data: dict):
        chat_name = self.active_chat_name or "Karşı taraf"
        dlg = TelegramDeleteDialog(target_user_name=chat_name, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            db_id = msg_data.get("id")
            if dlg.delete_for_everyone:
                bot_id = msg_data.get("bot_id", self.current_bot_id)
                chat_id = msg_data.get("chat_id", self.active_chat_id)
                worker = self.bot_manager.get_worker(bot_id)
                if worker and worker.isRunning() and msg_data.get("message_id"):
                    worker.delete_message_async(chat_id, msg_data["message_id"])
                self.db.mark_message_deleted_telegram(db_id)
            else:
                self.db.mark_message_deleted_locally(db_id)

            self.render_messages(self.active_chat_id)
            self.refresh_chats()

    def on_delete_media_file_requested(self, message_db_id: int):
        msg = self.db.get_message(message_db_id)
        if msg and msg.get("media_path") and os.path.exists(msg["media_path"]):
            try:
                os.remove(msg["media_path"])
                QMessageBox.information(self, "Bilgi", "İndirilen dosya yerel diskten başarıyla silindi.")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Dosya silinemedi: {str(e)}")
        self.render_messages(self.active_chat_id)

    def on_message_deleted(self, bot_id: int, chat_id: int, message_id: int, success: bool, err: str):
        if not success:
            QMessageBox.warning(self, "Telegram Silme Uyarısı", f"Telegram'dan silinemedi (48 saat aşımı veya yetki yok):\n{err}")

    def on_toggle_deleted_by_sender(self, msg_data: dict):
        db_id = msg_data.get("id")
        current_state = bool(msg_data.get("is_deleted_by_sender"))
        new_state = 0 if current_state else 1
        self.db.mark_message_deleted_by_sender(db_id, new_state)
        self.render_messages(self.active_chat_id)

    def on_message_edited_by_remote(self, edit_data: dict):
        bot_id = edit_data.get("bot_id")
        chat_id = edit_data.get("chat_id")
        if bot_id == self.current_bot_id and chat_id == self.active_chat_id:
            self.render_messages(self.active_chat_id)
        self.refresh_chats()

    def on_message_reaction_received(self, rx_data: dict):
        bot_id = rx_data.get("bot_id")
        chat_id = rx_data.get("chat_id")
        if bot_id == self.current_bot_id and chat_id == self.active_chat_id:
            self.mark_visible_outgoing_bubbles_read()
            self.render_messages(self.active_chat_id)
        self.refresh_chats()

    # --- SOHBET VE LİSTE YÖNETİMİ ---
    def load_initial_bots(self):
        self.bot_selector.blockSignals(True)
        bots = self.db.get_bots()
        self.bot_selector.clear()
        for bot in bots:
            label = f"{bot.get('name', 'Bot')} (@{bot.get('username') or bot['id']})"
            self.bot_selector.addItem(label, bot["id"])
            if bot.get("is_active"):
                self.bot_manager.start_bot(bot["id"], bot["token"], bot.get("proxy"))
        self.bot_selector.blockSignals(False)

        if self.bot_selector.count() > 0:
            self.current_bot_id = self.bot_selector.currentData()
            self.refresh_chats()
        else:
            self.current_bot_id = None
            self.status_badge.setText("Bot Eklenmedi")
            self.refresh_chats()

    def open_bot_manage_dialog(self):
        dlg = BotManageDialog(db=self.db, bot_manager=self.bot_manager, parent=self)
        dlg.bots_updated.connect(self.load_initial_bots)
        dlg.exec()

    def open_network_shield_settings(self):
        dlg = NetworkShieldSettingsDialog(
            net_mgr=self.net_manager,
            bot_manager=self.bot_manager,
            main_window=self,
            parent=self
        )
        dlg.exec()
        self.update_network_shield_button()

    def set_network_frozen_ui(self, is_frozen: bool, message: str = ""):
        self.network_freeze_banner.setVisible(is_frozen)
        if message:
            self.network_freeze_banner_label.setText(f"🔒 {message}")
        if is_frozen:
            self.msg_input.setEnabled(False)
            self.btn_send.setEnabled(False)
            self.msg_input.setPlaceholderText("Ağ tüneli değiştiriliyor (trafik donduruldu)...")
        else:
            self.msg_input.setEnabled(True)
            self.btn_send.setEnabled(True)
            self.msg_input.setPlaceholderText("Bir mesaj yazın... (Enter: Gönder, Shift+Enter: Yeni Satır)")
        self.update_network_shield_button()

    def update_network_shield_button(self):
        if not hasattr(self, 'net_manager') or not self.net_manager:
            return
        mode = self.net_manager.mode
        if mode == ShieldMode.HYBRID:
            self.btn_network_shield.setText("🟣 Kalkan: Hibrit")
            self.btn_network_shield.setStyleSheet("background-color: rgba(207, 159, 255, 0.16); color: #cf9fff; border: 1px solid rgba(207, 159, 255, 0.38); border-radius: 16px; font-weight: 600; padding: 4px 14px; font-size: 12px;")
        elif mode == ShieldMode.PROXY:
            self.btn_network_shield.setText("🟡 Kalkan: Proxy")
            self.btn_network_shield.setStyleSheet("background-color: rgba(245, 176, 65, 0.16); color: #f5b041; border: 1px solid rgba(245, 176, 65, 0.38); border-radius: 16px; font-weight: 600; padding: 4px 14px; font-size: 12px;")
        elif mode == ShieldMode.TOR:
            self.btn_network_shield.setText("🧅 Kalkan: Tor")
            self.btn_network_shield.setStyleSheet("background-color: rgba(62, 164, 202, 0.16); color: #3ea4ca; border: 1px solid rgba(62, 164, 202, 0.38); border-radius: 16px; font-weight: 600; padding: 4px 14px; font-size: 12px;")
        else:
            self.btn_network_shield.setText("⚪ Kalkan: Düz Bağlantı")
            self.btn_network_shield.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); color: #d1dbe5; border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 16px; font-weight: 600; padding: 4px 14px; font-size: 12px;")

    def open_user_profile_dialog(self):
        if not self.current_bot_id or not self.active_chat_id:
            return
        self.open_user_profile_dialog_for_chat(self.active_chat_id)

    def open_user_profile_dialog_for_chat(self, chat_id: int):
        if not self.current_bot_id or not chat_id:
            return
        dlg = UserProfileDialog(self.current_bot_id, chat_id, self.db, self.bot_manager, parent=self)
        dlg.note_updated.connect(self.on_profile_note_updated)
        dlg.exec()

    def on_profile_note_updated(self, note: str):
        if self.active_chat_id:
            cleaned = (note or "").strip()
            if cleaned:
                self.note_label.setText(f"📝 {cleaned}")
                self.note_label.setVisible(True)
            else:
                self.note_label.setText("")
                self.note_label.setVisible(False)
        self.refresh_chats()

    def update_header_avatar(self, avatar_path: str, name: str):
        if avatar_path and os.path.exists(avatar_path):
            pix = make_circular_pixmap(QPixmap(avatar_path), 42)
            self.avatar_label.setText("")
            self.avatar_label.setStyleSheet("background: transparent; border: none; padding: 0px;")
            self.avatar_label.setPixmap(pix)
        else:
            initial = name[0].upper() if name and name.strip() and name.strip() != "." else "?"
            self.avatar_label.setPixmap(QPixmap())
            self.avatar_label.setText(initial)
            self.avatar_label.setStyleSheet("""
                background-color: #5288c1;
                color: white;
                border-radius: 21px;
                border: none;
            """)

    def on_user_profile_fetched(self, bot_id: int, chat_id: int, data: dict):
        if bot_id != self.current_bot_id:
            return

        # If it's the currently open chat, update the header dynamically
        if self.active_chat_id == chat_id:
            name = data.get("sender_name")
            if name:
                self.active_chat_name = name
                self.chat_title.setText(name)
            uname = data.get("username")
            if uname is not None:
                if uname:
                    self.chat_uname_label.setText(f"@{uname}")
                    self.chat_uname_label.setVisible(True)
                else:
                    self.chat_uname_label.setText("")
                    self.chat_uname_label.setVisible(False)
            avatar_path = data.get("avatar_path") or ""
            self.update_header_avatar(avatar_path, self.active_chat_name)

        # Refresh chat list to update thumbnail/name/username
        self.refresh_chats()

    def toggle_spam_protection(self):
        self.spam_protector.enabled = not self.spam_protector.enabled
        if self.spam_protector.enabled:
            self.btn_toggle_spam.setText("🛡️ Spam Koruması: AÇIK")
            self.btn_toggle_spam.setStyleSheet("background-color: rgba(76, 217, 100, 0.18); color: #4cd964; border: 1px solid rgba(76, 217, 100, 0.4); border-radius: 8px; font-weight: 600; padding: 6px 14px;")
            QToolTip.showText(self.btn_toggle_spam.mapToGlobal(QPoint(0, 32)), "🛡️ Spam Koruması Açık (Hızlı flood ve tekrar filtreleri aktif)", self.btn_toggle_spam)
        else:
            self.btn_toggle_spam.setText("🛡️ Spam Koruması: KAPALI")
            self.btn_toggle_spam.setStyleSheet("background-color: rgba(255, 107, 107, 0.18); color: #ff6b6b; border: 1px solid rgba(255, 107, 107, 0.4); border-radius: 8px; font-weight: 600; padding: 6px 14px;")
            QToolTip.showText(self.btn_toggle_spam.mapToGlobal(QPoint(0, 32)), "⚠️ Spam Koruması Kapatıldı", self.btn_toggle_spam)

    def toggle_stealth_typing(self):
        self.stealth_typing = not self.stealth_typing
        if self.stealth_typing:
            self.btn_stealth_mode.setText("🤫 Yazıyor: Gizli")
            self.btn_stealth_mode.setStyleSheet("background-color: rgba(245, 176, 65, 0.16); color: #f5b041; border: 1px solid rgba(245, 176, 65, 0.38); border-radius: 16px; font-weight: 600; padding: 4px 14px; font-size: 12px;")
            QToolTip.showText(self.btn_stealth_mode.mapToGlobal(QPoint(0, 32)), "🤫 Gizli Mod: Karşı tarafa 'yazıyor...' bildirimi gönderilmeyecek", self.btn_stealth_mode)
        else:
            self.btn_stealth_mode.setText("💬 Yazıyor: Açık")
            self.btn_stealth_mode.setStyleSheet("")
            QToolTip.showText(self.btn_stealth_mode.mapToGlobal(QPoint(0, 32)), "💬 'Yazıyor...' bildirimi aktif", self.btn_stealth_mode)

    def on_bot_selection_changed(self):
        bot_id = self.bot_selector.currentData()
        if bot_id:
            self.current_bot_id = bot_id
            self.cancel_active_action()
            self.show_no_chat_selected_state()
            self.refresh_chats()

    def on_bot_status_changed(self, bot_id: int, is_online: bool, info: str):
        if bot_id == self.current_bot_id:
            if is_online:
                self.status_badge.setText(f"🟢 {info}")
                self.status_badge.setObjectName("statusBadgeOnline")
            else:
                self.status_badge.setText(f"🔴 {info}")
                self.status_badge.setObjectName("statusBadgeOffline")
            self.status_badge.setStyle(self.status_badge.style())

    def on_spam_detected(self, bot_id: int, chat_id: int, reason: str):
        is_perm = "kalıcı" in reason.lower()
        if is_perm and bot_id == self.current_bot_id and chat_id == self.active_chat_id:
            self.btn_block_toggle.setText("Engeli Kaldır")
            self.btn_block_toggle.setStyleSheet("background-color: #2e7d32;")
        self.refresh_chats()
        title = "🛡️ Kalıcı Spam Engeli" if is_perm else "⏳ Geçici Hız Sınırı (Mola)"
        QMessageBox.warning(self, title, f"Kullanıcı ({chat_id}):\n{reason}")

    def on_message_received(self, msg_data: dict):
        bot_id = msg_data["bot_id"]
        chat_id = msg_data["chat_id"]

        self.db.get_or_create_chat(
            bot_id=bot_id,
            chat_id=chat_id,
            sender_name=msg_data["sender_name"],
            username=msg_data["username"]
        )
        db_id = self.db.save_message(
            bot_id=bot_id,
            chat_id=chat_id,
            message_id=msg_data["message_id"],
            is_outgoing=0,
            text=msg_data.get("text", ""),
            media_type=msg_data.get("media_type"),
            media_path=msg_data.get("media_path"),
            file_name=msg_data.get("file_name"),
            reply_to_text=msg_data.get("reply_to_text"),
            timestamp=msg_data.get("timestamp")
        )
        msg_data["id"] = db_id

        # Mark all prior outgoing messages in this chat as read (recipient replied!)
        self.db.mark_outgoing_messages_as_read(bot_id, chat_id, msg_data.get("timestamp"))

        if bot_id == self.current_bot_id:
            if self.active_chat_id == chat_id:
                self.mark_visible_outgoing_bubbles_read()
                self.append_message_bubble(msg_data)
                self.update_chat_header_status(msg_data.get("timestamp"))
                self.scroll_to_bottom()
            else:
                self.unread_counts[chat_id] = self.unread_counts.get(chat_id, 0) + 1
            self.refresh_chats()

    def mark_visible_outgoing_bubbles_read(self):
        for i in range(self.messages_layout.count() - 1):
            row_item = self.messages_layout.itemAt(i)
            if row_item and row_item.widget():
                for b in row_item.widget().findChildren(MessageBubbleWidget):
                    if b.is_outgoing and not b.is_read:
                        b.set_read(True)

    def on_toggle_read_status(self, db_id: int, is_read: bool):
        self.db.set_message_read(db_id, 1 if is_read else 0)

    def on_message_sent(self, bot_id: int, chat_id: int, text: str, success: bool, err: str,
                        msg_id: int, media_type: str, media_path: str, reply_to_text: str):
        if not success:
            QMessageBox.critical(self, "Mesaj Gönderilemedi", f"Hata: {err}")
            return

        file_name = Path(media_path).name if media_path else None
        db_id = self.db.save_message(
            bot_id=bot_id,
            chat_id=chat_id,
            message_id=msg_id,
            is_outgoing=1,
            text=text,
            media_type=media_type or None,
            media_path=media_path or None,
            file_name=file_name,
            reply_to_text=reply_to_text or None,
            is_read=0
        )

        if bot_id == self.current_bot_id and chat_id == self.active_chat_id:
            self.append_message_bubble({
                "id": db_id,
                "bot_id": bot_id,
                "chat_id": chat_id,
                "message_id": msg_id,
                "is_outgoing": 1,
                "is_read": 0,
                "text": text,
                "media_type": media_type or None,
                "media_path": media_path or None,
                "file_name": file_name,
                "reply_to_text": reply_to_text or None,
                "timestamp": int(time.time())
            })
            self.scroll_to_bottom()
            self.refresh_chats()

    def on_chat_selected(self, item: QListWidgetItem):
        chat_id = item.data(Qt.ItemDataRole.UserRole)
        if not chat_id:
            return

        self.active_chat_id = chat_id
        self.unread_counts[chat_id] = 0

        chat = self.db.get_chat(self.current_bot_id, chat_id) or {}

        self.active_chat_name = chat.get("sender_name") or "Kullanıcı"
        uname = chat.get("username") or ""
        note = chat.get("custom_note") or ""
        is_pinned = bool(chat.get("is_pinned"))
        is_blocked = bool(chat.get("is_blocked"))
        avatar_path = chat.get("avatar_path") or ""

        # Update Header Elements
        self.chat_title.setText(self.active_chat_name)
        if uname:
            self.chat_uname_label.setText(f"@{uname}")
            self.chat_uname_label.setVisible(True)
        else:
            self.chat_uname_label.setText("")
            self.chat_uname_label.setVisible(False)
        self.id_badge_btn.setText(f"ID: {chat_id} 📋")
        self.id_badge_btn.setVisible(True)
        if note:
            self.note_label.setText(f"📝 {note}")
            self.note_label.setVisible(True)
        else:
            self.note_label.setText("")
            self.note_label.setVisible(False)

        self.update_header_avatar(avatar_path, self.active_chat_name)
        self.update_chat_header_status()

        # Update input placeholder for the active chat
        self.msg_input.setPlaceholderText(f"{self.active_chat_name} kullanıcısına mesaj yazın... (Enter: Gönder, Shift+Enter: Yeni Satır)")

        # Trigger background profile refresh from Telegram
        worker = self.bot_manager.get_worker(self.current_bot_id)
        if worker and worker.isRunning():
            worker.fetch_user_profile_async(chat_id)

        # Toggle Button States
        self.btn_profile.setVisible(True)
        self.btn_pin.setVisible(True)
        self.btn_pin.setText("📌 Sabitlendi" if is_pinned else "📌 Sabitle")
        self.btn_pin.setStyleSheet("background-color: #2b5278; color: #ffffff; border: 1px solid #5288c1; border-radius: 8px; font-weight: 600;" if is_pinned else "")

        self.btn_add_note.setVisible(True)
        self.btn_export.setVisible(True)
        self.btn_search_chat.setVisible(True)
        self.close_chat_search()

        self.btn_block_toggle.setVisible(True)
        if is_blocked:
            self.btn_block_toggle.setText("Engeli Kaldır")
            self.btn_block_toggle.setStyleSheet("background-color: rgba(76, 217, 100, 0.2); color: #4cd964; border: 1px solid rgba(76, 217, 100, 0.4); border-radius: 8px; font-weight: 600;")
        else:
            self.btn_block_toggle.setText("Engelle")
            self.btn_block_toggle.setStyleSheet("background-color: rgba(235, 87, 87, 0.2); color: #ff6b6b; border: 1px solid rgba(235, 87, 87, 0.4); border-radius: 8px; font-weight: 600;")

        self.cancel_active_action()
        self.render_messages(chat_id)
        self.refresh_chats()

    def toggle_active_chat_block(self):
        if not self.current_bot_id or not self.active_chat_id:
            return

        is_currently_blocked = self.db.is_chat_blocked(self.current_bot_id, self.active_chat_id)
        new_status = 0 if is_currently_blocked else 1
        self.db.toggle_block_chat(self.current_bot_id, self.active_chat_id, new_status)

        if new_status:
            self.btn_block_toggle.setText("Engeli Kaldır")
            self.btn_block_toggle.setStyleSheet("background-color: rgba(76, 217, 100, 0.2); color: #4cd964; border: 1px solid rgba(76, 217, 100, 0.4); border-radius: 8px; font-weight: 600;")
        else:
            self.btn_block_toggle.setText("Engelle")
            self.btn_block_toggle.setStyleSheet("background-color: rgba(235, 87, 87, 0.2); color: #ff6b6b; border: 1px solid rgba(235, 87, 87, 0.4); border-radius: 8px; font-weight: 600;")
            self.spam_protector.reset_user(self.current_bot_id, self.active_chat_id)

        tip_text = "Kullanıcı engellendi!" if new_status else "Kullanıcının engeli kaldırıldı!"
        QToolTip.showText(self.btn_block_toggle.mapToGlobal(QPoint(0, 32)), tip_text, self.btn_block_toggle)
        self.refresh_chats()

    def show_chat_context_menu(self, pos):
        item = self.chat_list_widget.itemAt(pos)
        if not item:
            return
        chat_id = item.data(Qt.ItemDataRole.UserRole)
        chats = self.db.get_chats_for_bot(self.current_bot_id)
        chat = next((c for c in chats if c["chat_id"] == chat_id), {})
        is_blocked = bool(chat.get("is_blocked"))
        is_pinned = bool(chat.get("is_pinned"))

        menu = QMenu(self)

        act_profile = QAction("👤 Profili ve Medyaları Gör", self)
        act_profile.triggered.connect(lambda: self.open_user_profile_dialog_for_chat(chat_id))
        menu.addAction(act_profile)

        menu.addSeparator()

        pin_text = "📌 Sabitlemeyi Kaldır" if is_pinned else "📌 Başa Sabitle"
        act_pin = QAction(pin_text, self)
        act_pin.triggered.connect(lambda: self.toggle_chat_pin_by_id(chat_id, not is_pinned))
        menu.addAction(act_pin)

        act_note = QAction("📝 Özel Not Düzenle", self)
        act_note.triggered.connect(lambda: self.edit_chat_note_by_id(chat_id))
        menu.addAction(act_note)

        act_copy_id = QAction("📋 Kullanıcı ID'sini Kopyala", self)
        def on_copy_cid():
            QApplication.clipboard().setText(str(chat_id))
            QToolTip.showText(self.chat_list_widget.mapToGlobal(pos), "ID Kopyalandı!", self.chat_list_widget)
        act_copy_id.triggered.connect(on_copy_cid)
        menu.addAction(act_copy_id)

        menu.addSeparator()

        block_text = "✅ Engeli Kaldır" if is_blocked else "🚫 Kullanıcıyı Engelle"
        act_block = QAction(block_text, self)
        act_block.triggered.connect(lambda: self.toggle_chat_block_by_id(chat_id, not is_blocked))
        menu.addAction(act_block)

        act_export = QAction("💾 Sohbeti Dışa Aktar (.txt)", self)
        act_export.triggered.connect(lambda: self.export_chat_by_id(chat_id))
        menu.addAction(act_export)

        menu.addSeparator()

        act_clear = QAction("🧹 Sohbet Geçmişini Temizle", self)
        act_clear.triggered.connect(lambda: self.clear_chat_history(chat_id))
        menu.addAction(act_clear)

        act_delete_chat = QAction("🗑️ Sohbeti Tamamen Sil", self)
        act_delete_chat.triggered.connect(lambda: self.delete_entire_chat_by_id(chat_id))
        menu.addAction(act_delete_chat)

        menu.exec(self.chat_list_widget.mapToGlobal(pos))

    def toggle_chat_pin_by_id(self, chat_id: int, new_status: bool):
        self.db.toggle_pin_chat(self.current_bot_id, chat_id, int(new_status))
        if self.active_chat_id == chat_id:
            self.btn_pin.setText("📌 Sabitlendi" if new_status else "📌 Sabitle")
            self.btn_pin.setStyleSheet("background-color: #2b5278; color: #ffffff; border: 1px solid #5288c1; border-radius: 8px; font-weight: 600;" if new_status else "")
        self.refresh_chats()

    def edit_chat_note_by_id(self, chat_id: int):
        chats = self.db.get_chats_for_bot(self.current_bot_id)
        chat = next((c for c in chats if c["chat_id"] == chat_id), {})
        cur_note = chat.get("custom_note") or ""
        name = chat.get("sender_name") or str(chat_id)

        new_note, ok = QInputDialog.getText(self, "Özel Not Düzenle", f"'{name}' için not/takma ad:", text=cur_note)
        if ok:
            cleaned = new_note.strip()
            self.db.set_chat_note(self.current_bot_id, chat_id, cleaned)
            if self.active_chat_id == chat_id:
                if cleaned:
                    self.note_label.setText(f"📝 {cleaned}")
                    self.note_label.setVisible(True)
                else:
                    self.note_label.setText("")
                    self.note_label.setVisible(False)
            self.refresh_chats()

    def toggle_chat_block_by_id(self, chat_id: int, new_status: bool):
        self.db.toggle_block_chat(self.current_bot_id, chat_id, int(new_status))
        if not new_status:
            self.spam_protector.reset_user(self.current_bot_id, chat_id)
        if self.active_chat_id == chat_id:
            if new_status:
                self.btn_block_toggle.setText("Engeli Kaldır")
                self.btn_block_toggle.setStyleSheet("background-color: rgba(76, 217, 100, 0.2); color: #4cd964; border: 1px solid rgba(76, 217, 100, 0.4); border-radius: 8px; font-weight: 600;")
            else:
                self.btn_block_toggle.setText("Engelle")
                self.btn_block_toggle.setStyleSheet("background-color: rgba(235, 87, 87, 0.2); color: #ff6b6b; border: 1px solid rgba(235, 87, 87, 0.4); border-radius: 8px; font-weight: 600;")
        self.refresh_chats()

    def export_chat_by_id(self, chat_id: int):
        chats = self.db.get_chats_for_bot(self.current_bot_id)
        chat = next((c for c in chats if c["chat_id"] == chat_id), {})
        name = chat.get("sender_name") or str(chat_id)
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Sohbeti Dışa Aktar",
            f"sohbet_{chat_id}_{datetime.now().strftime('%Y%m%d')}.txt",
            "Metin Dosyaları (*.txt)"
        )
        if not file_path:
            return

        messages = self.db.get_messages(self.current_bot_id, chat_id)
        lines = [
            f"=== SOHBET GEÇMİŞİ ===",
            f"Kullanıcı: {name} (ID: {chat_id})",
            f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 30 + "\n"
        ]
        for m in messages:
            sender = "BOT (Siz)" if m["is_outgoing"] else name
            t_str = datetime.fromtimestamp(m["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            body = m["text"] or ""
            if m["media_type"]:
                body += f" [Dosya: {m['file_name'] or m['media_type']}]"
            lines.append(f"[{t_str}] {sender}: {body}")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        QMessageBox.information(self, "Başarılı", "Sohbet kaydedildi!")

    def clear_chat_history(self, chat_id: int):
        self.db.clear_chat_history(self.current_bot_id, chat_id)
        if self.active_chat_id == chat_id:
            self.render_messages(chat_id)
        self.refresh_chats()

    def delete_entire_chat_by_id(self, chat_id: int):
        reply = QMessageBox.question(
            self, "Sohbeti Sil",
            "Bu sohbeti ve tüm mesaj geçmişini tamamen silmek istediğinize emin misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_entire_chat(self.current_bot_id, chat_id)
            if self.active_chat_id == chat_id:
                self.show_no_chat_selected_state()
            self.refresh_chats()

    def refresh_chats(self):
        if not self.current_bot_id:
            self.chat_list_widget.clear()
            self.chat_list_widget.setVisible(False)
            self.left_empty_icon.setText("🤖")
            self.left_empty_label.setText("Henüz bot eklenmedi.\nYukarıdaki 'Bot Yönetimi' butonundan ilk botunuzu ekleyin.")
            self.left_empty_frame.setVisible(True)
            return

        filter_text = self.search_input.text().lower()
        self.chat_list_widget.clear()
        chats = self.db.get_chats_for_bot(self.current_bot_id)

        matched_count = 0
        for chat in chats:
            name = chat.get("sender_name") or "Anonim"
            uname = chat.get("username") or ""
            chat_id = chat["chat_id"]
            is_pinned = bool(chat.get("is_pinned"))
            is_blocked = bool(chat.get("is_blocked"))
            custom_note = chat.get("custom_note") or ""

            # Search filter (name, username, note, or ID)
            match_str = f"{name} {uname} {custom_note} {chat_id}".lower()
            if filter_text and filter_text not in match_str:
                continue

            matched_count += 1
            messages = self.db.get_messages(self.current_bot_id, chat_id)
            sub = f"@{uname}" if uname else f"ID: {chat_id}"
            if messages:
                last_m = messages[-1]
                if last_m.get("text"):
                    sub = last_m["text"][:26] + "..." if len(last_m["text"]) > 26 else last_m["text"]
                elif last_m.get("media_type"):
                    sub = f"[{last_m['media_type'].capitalize()}]"

            unread = self.unread_counts.get(chat_id, 0)
            item_widget = ChatItemWidget(
                title=name,
                subtitle=sub,
                is_pinned=is_pinned,
                custom_note=custom_note,
                is_blocked=is_blocked,
                unread_count=unread,
                avatar_path=chat.get("avatar_path") or ""
            )

            item = QListWidgetItem(self.chat_list_widget)
            item.setSizeHint(item_widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, chat_id)
            self.chat_list_widget.addItem(item)
            self.chat_list_widget.setItemWidget(item, item_widget)

            if chat_id == self.active_chat_id:
                self.chat_list_widget.setCurrentItem(item)

        if matched_count == 0:
            self.chat_list_widget.setVisible(False)
            if filter_text:
                self.left_empty_icon.setText("🔍")
                self.left_empty_label.setText(f"'{self.search_input.text()}' ile eşleşen sohbet bulunamadı.\nFarklı bir arama terimi deneyin.")
            elif not chats:
                self.left_empty_icon.setText("💬")
                self.left_empty_label.setText("Henüz sohbet yok.\nBota Telegram'dan mesaj geldiğinde burada listelenecektir.")
            else:
                self.left_empty_icon.setText("🔍")
                self.left_empty_label.setText("Eşleşen sohbet bulunamadı.")
            self.left_empty_frame.setVisible(True)
        else:
            self.left_empty_frame.setVisible(False)
            self.chat_list_widget.setVisible(True)

    def filter_chats(self):
        self.refresh_chats()

    def clear_messages_area(self):
        if AudioPlayerWidget._active_player:
            try:
                AudioPlayerWidget._active_player.stop_and_release()
            except Exception:
                pass
        self.last_rendered_date_str = None
        self.rendered_message_bubbles.clear()
        while self.messages_layout.count() > 1:
            child = self.messages_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def show_no_chat_selected_state(self):
        self.clear_messages_area()
        self.active_chat_id = None
        self.active_chat_name = ""
        self.chat_title.setText("Bir sohbet seçin")
        self.chat_uname_label.setText("")
        self.chat_uname_label.setVisible(False)
        self.chat_status_label.setText("")
        self.id_badge_btn.setText("ID: -")
        self.id_badge_btn.setVisible(False)
        self.note_label.setText("")
        self.note_label.setVisible(False)
        self.update_header_avatar("", "")
        self.btn_profile.setVisible(False)
        self.btn_pin.setVisible(False)
        self.btn_add_note.setVisible(False)
        self.btn_export.setVisible(False)
        self.btn_block_toggle.setVisible(False)
        self.btn_search_chat.setVisible(False)
        self.close_chat_search()
        self.msg_input.setPlaceholderText("Mesajlaşmaya başlamak için soldan bir sohbet seçin...")

        # Centered Welcome Badge
        welcome_frame = QFrame()
        welcome_frame.setObjectName("welcomeEmptyBadge")
        welcome_frame.setStyleSheet("""
            QFrame#welcomeEmptyBadge {
                background-color: rgba(23, 33, 43, 0.88);
                border: 1px solid rgba(82, 136, 193, 0.25);
                border-radius: 16px;
                padding: 18px 26px;
            }
        """)
        w_layout = QVBoxLayout(welcome_frame)
        w_layout.setContentsMargins(18, 16, 18, 16)
        w_layout.setSpacing(8)
        w_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel("💬")
        icon_lbl.setFont(QFont("Segoe UI", 24))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w_layout.addWidget(icon_lbl)

        title_lbl = QLabel("Sohbet Başlatmak İçin Soldan Bir Kullanıcı Seçin")
        title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #ffffff;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w_layout.addWidget(title_lbl)

        sub_lbl = QLabel("Gelen mesajları görüntülemek, yanıtlamak veya dosya göndermek için sol listeden bir sohbet seçin.")
        sub_lbl.setFont(QFont("Segoe UI", 9))
        sub_lbl.setStyleSheet("color: #7f91a4;")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setWordWrap(True)
        w_layout.addWidget(sub_lbl)

        center_row = QHBoxLayout()
        center_row.addStretch(1)
        center_row.addWidget(welcome_frame)
        center_row.addStretch(1)

        wrapper = QWidget()
        wrapper.setObjectName("noChatWrapper")
        wrapper.setLayout(center_row)

        self.messages_layout.insertWidget(0, wrapper)

    def render_messages(self, chat_id: int):
        self.clear_messages_area()
        messages = self.db.get_messages(self.current_bot_id, chat_id)
        if not messages:
            empty_chat_frame = QFrame()
            empty_chat_frame.setObjectName("emptyChatBadge")
            empty_chat_frame.setStyleSheet("""
                QFrame#emptyChatBadge {
                    background-color: rgba(23, 33, 43, 0.88);
                    border: 1px solid rgba(82, 136, 193, 0.25);
                    border-radius: 14px;
                    padding: 14px 22px;
                }
            """)
            ec_layout = QVBoxLayout(empty_chat_frame)
            ec_layout.setContentsMargins(14, 12, 14, 12)
            ec_layout.setSpacing(4)
            ec_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            ec_title = QLabel(f"💬 {self.active_chat_name} ile henüz mesaj yok")
            ec_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            ec_title.setStyleSheet("color: #ffffff;")
            ec_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ec_layout.addWidget(ec_title)

            ec_sub = QLabel("Aşağıdaki kutudan ilk mesajınızı yazarak sohbeti başlatabilirsiniz.")
            ec_sub.setFont(QFont("Segoe UI", 9))
            ec_sub.setStyleSheet("color: #7f91a4;")
            ec_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ec_layout.addWidget(ec_sub)

            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(empty_chat_frame)
            row.addStretch(1)

            wrapper = QWidget()
            wrapper.setObjectName("emptyChatWrapper")
            wrapper.setLayout(row)
            self.messages_layout.insertWidget(0, wrapper)
            return

        for msg in messages:
            self.append_message_bubble(msg)
        QTimer.singleShot(40, self.scroll_to_bottom)

    def append_date_separator(self, date_text: str):
        lbl = QLabel(date_text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        lbl.setStyleSheet("""
            QLabel {
                background-color: rgba(23, 33, 43, 0.85);
                color: #829bb0;
                border-radius: 11px;
                padding: 4px 14px;
            }
        """)
        row = QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 6)
        row.addStretch(1)
        row.addWidget(lbl)
        row.addStretch(1)
        row_widget = QWidget()
        row_widget.setLayout(row)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, row_widget)

    def append_message_bubble(self, msg_data: dict):
        # Remove empty chat / no chat placeholder if present
        for i in range(self.messages_layout.count()):
            item = self.messages_layout.itemAt(i)
            if item and item.widget() and item.widget().objectName() in ("emptyChatWrapper", "noChatWrapper"):
                w = item.widget()
                self.messages_layout.removeWidget(w)
                w.deleteLater()
                break

        ts = msg_data.get("timestamp") or int(time.time())
        msg_date = datetime.fromtimestamp(ts).date()
        today = datetime.now().date()
        if msg_date == today:
            date_str = "Bugün"
        elif msg_date == today - timedelta(days=1):
            date_str = "Dün"
        else:
            months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", 
                      "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
            date_str = f"{msg_date.day} {months[msg_date.month - 1]} {msg_date.year}"

        if not hasattr(self, "last_rendered_date_str"):
            self.last_rendered_date_str = None

        if date_str != self.last_rendered_date_str:
            self.append_date_separator(date_str)
            self.last_rendered_date_str = date_str

        bubble = MessageBubbleWidget(msg_data)
        bubble.request_reply.connect(self.on_reply_requested)
        bubble.request_edit.connect(self.on_edit_requested)
        bubble.request_delete_dialog.connect(self.on_delete_dialog_requested)
        bubble.request_delete_media_file.connect(self.on_delete_media_file_requested)
        bubble.request_toggle_deleted_by_sender.connect(self.on_toggle_deleted_by_sender)
        bubble.request_toggle_read_status.connect(self.on_toggle_read_status)
        bubble.request_reaction.connect(self.on_reaction_requested)
        bubble.request_jump_to_message.connect(self.on_jump_to_message_requested)

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(12, 1, 12, 1)

        if msg_data.get("is_outgoing"):
            row_layout.addStretch(1)
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch(1)

        row_widget = QWidget()
        row_widget.setLayout(row_layout)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, row_widget)
        self.rendered_message_bubbles.append((msg_data, bubble, row_widget))

    def on_jump_to_message_requested(self, target_text: str):
        """Scrolls to target replied message in chat and flashes smooth highlight once."""
        if not target_text or not hasattr(self, "rendered_message_bubbles") or not self.rendered_message_bubbles:
            return
        clean_target = target_text.strip()
        matched_tuple = None

        # 1. Exact match (search backwards to find the message that was replied to)
        for msg_data, bubble, row_widget in reversed(self.rendered_message_bubbles):
            msg_txt = (msg_data.get("text") or "").strip()
            if msg_txt and msg_txt == clean_target:
                matched_tuple = (msg_data, bubble, row_widget)
                break

        # 2. Substring or prefix match if exact match wasn't found
        if not matched_tuple:
            for msg_data, bubble, row_widget in reversed(self.rendered_message_bubbles):
                msg_txt = (msg_data.get("text") or "").strip()
                if msg_txt and (clean_target in msg_txt or msg_txt in clean_target):
                    matched_tuple = (msg_data, bubble, row_widget)
                    break

        if matched_tuple:
            _, target_bubble, target_row = matched_tuple
            vbar = self.scroll_area.verticalScrollBar()
            start_val = vbar.value()

            # Calculate target scrollbar position to center target_row in viewport
            pos = target_row.mapTo(self.messages_container, QPoint(0, 0))
            viewport_h = self.scroll_area.viewport().height()
            row_h = target_row.height()
            target_val = max(0, min(vbar.maximum(), pos.y() - (viewport_h // 2) + (row_h // 2)))

            if abs(target_val - start_val) > 10:
                # Telegram-style smooth animated scroll
                if hasattr(self, "_scroll_anim") and self._scroll_anim.state() == QVariantAnimation.State.Running:
                    self._scroll_anim.stop()

                self._scroll_anim = QVariantAnimation(self)
                dist = abs(target_val - start_val)
                duration = min(450, max(280, int(dist * 0.4)))
                self._scroll_anim.setDuration(duration)
                self._scroll_anim.setStartValue(start_val)
                self._scroll_anim.setEndValue(target_val)
                self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                self._scroll_anim.valueChanged.connect(lambda v: vbar.setValue(int(v)))
                self._scroll_anim.finished.connect(target_bubble.flash_highlight)
                self._scroll_anim.start()
            else:
                target_bubble.flash_highlight()

    def scroll_to_bottom(self):
        vbar = self.scroll_area.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    def closeEvent(self, event):
        if AudioPlayerWidget._active_player:
            try:
                AudioPlayerWidget._active_player.stop_and_release()
            except Exception:
                pass
        self.bot_manager.stop_all()
        if hasattr(self, 'net_manager') and self.net_manager:
            try:
                self.net_manager.stop_tor_process()
            except Exception:
                pass
        try:
            QThreadPool.globalInstance().waitForDone(1000)
        except Exception:
            pass
        try:
            sec_mgr = DatabaseSecurityManager()
            if sec_mgr.is_vault_initialized():
                sec_mgr.encrypt_database()
        except Exception:
            pass
        event.accept()

    def apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0e1621;
            }
            #topBar {
                background-color: #17212b;
                border-bottom: 1px solid #101921;
            }
            #topBar QLabel {
                color: #e4ecf2;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
            QToolTip {
                background-color: #17212b;
                color: #ffffff;
                border: 1px solid rgba(82, 136, 193, 0.35);
                border-radius: 6px;
                padding: 6px 10px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QComboBox {
                background-color: #242f3d;
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                padding: 4px 14px;
                font-size: 12px;
                font-weight: 500;
                font-family: 'Segoe UI', sans-serif;
            }
            QComboBox:hover {
                background-color: #2b394a;
                border-color: #5288c1;
            }
            QComboBox::drop-down {
                border: none;
                width: 22px;
                padding-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #17212b;
                color: #ffffff;
                selection-background-color: #2b5278;
                selection-color: #ffffff;
                border: 1px solid #242f3d;
                border-radius: 8px;
                outline: none;
                padding: 4px;
            }
            QLineEdit, QTextEdit {
                background-color: #242f3d;
                color: #ffffff;
                border: 1px solid #2b394a;
                border-radius: 10px;
                padding: 7px 12px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus {
                background-color: #1c2733;
                border: 1px solid #5288c1;
            }
            #searchChatsInput {
                background-color: #242f3d;
                border: 1px solid transparent;
                border-radius: 16px;
                padding: 7px 14px;
                color: #ffffff;
                font-size: 12px;
                font-family: 'Segoe UI', sans-serif;
            }
            #searchChatsInput:hover {
                background-color: #2b394a;
            }
            #searchChatsInput:focus {
                background-color: #17212b;
                border: 1px solid #5288c1;
            }
            QPushButton {
                background-color: #242f3d;
                color: #d1dbe5;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 14px;
                padding: 5px 14px;
                font-family: 'Segoe UI', 'Segoe UI Emoji', sans-serif;
                font-weight: 500;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2b5278;
                color: #ffffff;
                border-color: #5288c1;
            }
            QPushButton:pressed {
                background-color: #1c2733;
            }
            QPushButton:disabled {
                background-color: #1c2733;
                color: #5c6e82;
                border-color: transparent;
            }
            #btnSend {
                background-color: #5288c1;
                color: #ffffff;
                border: none;
                border-radius: 19px;
                font-family: 'Segoe UI', sans-serif;
                font-weight: 600;
                font-size: 13px;
                padding: 0 18px;
            }
            #btnSend:hover { background-color: #649ad4; }
            #btnSend:pressed { background-color: #3f6fa3; }
            #btnAttach, #btnQuick {
                background-color: transparent;
                color: #7f91a4;
                border: none;
                border-radius: 19px;
                padding: 0px;
                margin: 0px;
                font-family: 'Segoe UI Emoji', 'Noto Color Emoji', 'Apple Color Emoji', 'Segoe UI Symbol', sans-serif;
                font-weight: normal;
                font-size: 19px;
            }
            #btnAttach:hover, #btnQuick:hover {
                background-color: #242f3d;
                color: #5288c1;
            }
            #btnAttach:pressed, #btnQuick:pressed {
                background-color: #1c2733;
            }
            #btnEmoji {
                background-color: transparent;
                color: #7f91a4;
                border: none;
                border-radius: 19px;
                padding: 0px;
                margin: 0px;
                font-family: 'Segoe UI Emoji', 'Noto Color Emoji', 'Apple Color Emoji', sans-serif;
                font-weight: normal;
                font-size: 20px;
            }
            #btnEmoji:hover {
                background-color: #242f3d;
                color: #f0c040;
            }
            #btnEmoji:pressed {
                background-color: #1c2733;
            }
            #msgInput {
                background-color: #242f3d;
                color: #ffffff;
                border: 1px solid #2b394a;
                border-radius: 18px;
                padding: 8px 14px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            #msgInput:focus {
                background-color: #1c2733;
                border: 1px solid #5288c1;
            }
            #statusBadgeOffline {
                background-color: rgba(255, 107, 107, 0.12);
                color: #ff6b6b;
                border: 1px solid rgba(255, 107, 107, 0.32);
                border-radius: 14px;
                padding: 3px 12px;
                font-weight: 600;
                font-size: 11px;
            }
            #statusBadgeOnline {
                background-color: rgba(76, 217, 100, 0.12);
                color: #4cd964;
                border: 1px solid rgba(76, 217, 100, 0.32);
                border-radius: 14px;
                padding: 3px 12px;
                font-weight: 600;
                font-size: 11px;
            }
            #leftPanel {
                background-color: #17212b;
                border-right: 1px solid #101921;
            }
            #chatList {
                background-color: transparent;
                border: none;
                outline: none;
            }
            #chatList::item {
                background-color: transparent;
                border-radius: 10px;
                margin: 2px 6px;
                padding: 0px;
            }
            #chatList::item:hover {
                background-color: #202b36;
            }
            #chatList::item:selected {
                background-color: #2b5278;
            }
            #rightPanel {
                background-color: #0e1621;
            }
            #chatHeader {
                background-color: #17212b;
                border-bottom: 1px solid #101921;
            }
            #chatHeader QLabel { color: #ffffff; }
            #chatHeader QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                color: #d1dbe5;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 500;
                min-height: 28px;
            }
            #chatHeader QPushButton:hover {
                background-color: #2b5278;
                color: #ffffff;
                border-color: #5288c1;
            }
            #chatHeader QPushButton:pressed {
                background-color: #1c2733;
            }
            #messageArea {
                background-color: #0e1621;
                border: none;
            }
            #inputFrame {
                background-color: #17212b;
                border-top: 1px solid #101921;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.16);
                border-radius: 3px;
                min-height: 28px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(82, 136, 193, 0.7);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                height: 0px;
            }
            QSplitter::handle {
                background-color: #101921;
                width: 1px;
            }
            QMenu {
                background-color: #17212b;
                color: #ffffff;
                border: 1px solid #242f3d;
                border-radius: 10px;
                padding: 6px;
            }
            QMenu::item {
                padding: 7px 18px;
                border-radius: 6px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #2b5278;
            }
            QMenu::separator {
                height: 1px;
                background-color: #242f3d;
                margin: 4px 8px;
            }
        """)


def main():
    app = QApplication(sys.argv)
    sec_mgr = DatabaseSecurityManager()

    if sec_mgr.is_vault_initialized():
        unlock_dlg = MasterPasswordUnlockDialog(sec_mgr)
        if unlock_dlg.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)
    else:
        setup_dlg = MasterPasswordSetupDialog(sec_mgr)
        if setup_dlg.exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)

    # 2. Network Anonymity Shield Selection (Freezes all traffic until mode is established)
    net_mgr = NetworkShieldManager(is_frozen=True)
    shield_dlg = NetworkShieldStartupDialog(net_mgr)
    if shield_dlg.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)

    window = MainWindow(net_manager=net_mgr)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
