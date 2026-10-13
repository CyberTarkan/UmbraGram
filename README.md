# UmbraGram

<p align="center">
  <a href="#english">English</a> •
  <a href="#türkçe">Türkçe</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/GUI-PyQt6-green.svg" alt="PyQt6">
  <img src="https://img.shields.io/badge/Network-Tor%20SOCKS5-purple.svg" alt="Tor">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

---

<a name="english"></a>
## English

**UmbraGram** is a security-hardened, privacy-centric desktop Telegram bot workstation built with Python and PyQt6. Designed for research in operational privacy, network traffic obfuscation, and anti-forensics, it combines network layer isolation with hardware-aware data sanitization and linguistic stylometry defense.

### Key Features

* **🛡️ Network Shield & Traffic Obfuscation:**
  * **Tor Onion Routing:** Automated discovery and background headless execution of local `tor.exe` instances, establishing SOCKS5 circuits on `127.0.0.1:9050`.
  * **Dynamic Elite Proxy Chaining:** Multi-threaded verification of public and custom proxy pools (SOCKS5/HTTP) with automatic failover and latency tracking.
  * **Fail-Closed Kill Switch:** Automatically severs all outbound network worker threads if the proxy tunnel or Tor circuit drops, preventing real IP leaks.
  * **Microsecond Timing Jitter:** Injects non-deterministic, configurable millisecond delays into outgoing packets to defeat ISP-level traffic timing correlation attacks.

* **🧹 Linguistic Stylometry Neutralizer (`TextNeutralizer`):**
  * **Rule-Based Forensic Stylometry Defense:** Transforms idiosyncratic conversational text into neutral, standardized formal language.
  * **Dialect & Shorthand Elimination:** Strips Turkish SMS abbreviations, irregular vowel elongations (e.g., `selaaamm` $\to$ `selam`), vocative slang, profanities, and erratic punctuation.
  * **Keyboard Shortcut:** Instant neutralization accessible via `Ctrl+Shift+N` or the inline `🪄` interface action.

* **💽 Hardware-Aware Forensic Sanitization (`shredder.py`):**
  * **Physical Architecture Detection:** Queries physical disk controllers to distinguish magnetic platters (HDD) from flash memory (NVMe/SSD).
  * **HDD Mode:** Multi-pass DoD overwrite sequence (`os.urandom` + `0x00` + `0xFF`) accompanied by low-level `os.fsync` flushes to neutralize magnetic remnant traces.
  * **NVMe / SSD Mode:** Applies high-entropy single-pass overwrite combined with zero-byte truncation (`truncate(0)`) to signal OS-level TRIM deallocation, mitigating Flash Translation Layer (FTL) wear-leveling data remnants.
  * **Emergency Self-Destruct:** One-touch cryptographic key erasure and database wipe triggered via `Ctrl+Alt+Shift+X`.

* **📷 Automated Media & Document De-identification:**
  * **EXIF & GPS Stripping:** Strips camera metadata, GPS coordinates, device identifiers, and editing software headers from outgoing images.
  * **Document Scrubbing:** Cleans PDF author, producer, and creation date fields prior to upload.
  * **Pre-Flight Visual Inspection:** Displays a security verification prompt before dispatching images.

* **⚡ Engine & Chat Management:**
  * **Multi-Bot Orchestration:** Concurrent polling across multiple bot tokens with isolated session threads.
  * **Spam & Flooding Protection:** Adaptive rate limiting with sliding-window tracking, identical message throttling, and temporary cooldown locks.
  * **Encrypted Local Storage:** Thread-safe SQLite database schema supporting custom notes, pinning, and full conversation removal.

### Project Structure

```
UmbraGram/
├── main.py                   # PyQt6 desktop application & UI entrypoint
├── network_manager.py        # Tor controller, proxy pool & packet jitter
├── text_neutralizer.py       # Linguistic stylometry neutralization engine
├── shredder.py               # Hardware-differentiated forensic data shredder
├── telegram_service.py       # Telegram Bot API workers & media scrubbers
├── db_manager.py             # Encrypted database management
├── spam_protector.py         # Anti-spam & sliding window rate limiter
├── tests/                    # Comprehensive unit & functional test suite
├── requirements.txt          # Python dependency specifications
└── run.bat                   # Quick launcher script for Windows
```

### Installation & Usage

1. **Clone the repository:**
   ```bash
   git clone https://github.com/CyberTarkan/UmbraGram.git
   cd UmbraGram
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application:**
   ```bash
   python main.py
   ```

### Running Tests

```bash
pytest tests/ -v
```

### Disclaimer & Terms of Use

> [!WARNING]
> This software is provided strictly for educational, defensive research, and authorized security auditing purposes. The developers, contributors, and maintainers accept **no responsibility or liability** for any direct or indirect damage, misuse, illegal activities, or violations of third-party Terms of Service (including Telegram's Terms of Service) resulting from the use of this software. End users are solely responsible for ensuring that their deployment complies with all applicable local, national, and international laws and regulations.

---

<a name="türkçe"></a>
## Türkçe

**UmbraGram**, Python ve PyQt6 ile geliştirilmiş, güvenlik ve mahremiyet odaklı masaüstü Telegram bot istemcisidir. Operasyonel gizlilik, ağ trafiğini gizleme ve adli bilişime karşı koyma (anti-forensics) araştırmaları için tasarlanmış olup; ağ katmanı izolasyonunu, donanıma duyarlı veri imhasını ve dilbilimsel stilometri (üslup) savunmasını tek çatı altında birleştirir.

### Temel Özellikler

* **🛡️ Ağ Kalkanı & Trafik Karıştırma:**
  * **Tor Onion Yönlendirmesi:** Sistemdeki `tor.exe` dosyasını otomatik tespit eder, arka planda sessizce başlatır ve `127.0.0.1:9050` üzerinden SOCKS5 devresi kurar.
  * **Dinamik Proxy Havuzu:** Çok iş parçacıklı (multi-threaded) proxy havuzu testi, otomatik hata toleransı ve gecikme takibi.
  * **Kill Switch (Acil Şalter):** Proxy bağlantısı veya Tor devresi koptuğunda tüm ağ isteklerini anında dondurarak gerçek IP sızıntısını engeller.
  * **Milisaniye Paket Jitter'ı:** Çıkış paketlerine rastgele milisaniye gecikmeleri ekleyerek İSS düzeyindeki zaman korelasyonu (Timing Attack) analizlerini bozar.

* **🧹 Dilbilimsel Stilometri Nötralizasyonu (`TextNeutralizer`):**
  * **Kural Tabanlı Üslup Temizliği:** Kişiye özgü yazım alışkanlıklarını standart ve tarafsız bir resmi Türkçe diline dönüştürür.
  * **Argo ve Kısaltma Ayıklama:** Mesajlaşma kısaltmalarını (`slm`, `nbr`, `tmm`), uzatılmış harfleri (`selaaam` $\to$ `selam`), hitap jargonlarını (`kanka`, `reis`, `hocam`), küfürleri ve düzensiz noktalama işaretlerini temizler.
  * **Kısayol Desteği:** `Ctrl+Shift+N` kısayolu veya arayüzdeki `🪄` butonuyla tek tıkla nötralizasyon.

* **💽 Donanıma Duyarlı Adli İmha (`shredder.py`):**
  * **Fiziksel Disk Tespiti:** Sistemin manyetik disk (HDD) mi yoksa flash bellek (NVMe/SSD) mi olduğunu fiziksel denetleyiciden tespit eder.
  * **HDD Modu:** Manyetik izleri silmek için çok geçişli DoD algoritması (`urandom` + `0x00` + `0xFF`) ve donanımsal önbellek boşaltma (`os.fsync`) uygular.
  * **NVMe / SSD Modu:** Flash belleğin Aşınma Dengeleme (Wear-Leveling) ve FTL katmanını aşmak için yüksek entropili tek geçiş + sıfır bayt kırpma (`truncate(0)`) ile işletim sistemi düzeyinde TRIM/deallocate komutunu tetikler.
  * **Acil Durum İmhası:** `Ctrl+Alt+Shift+X` kısayoluyla tek tuşla veritabanını ve şifreleme anahtarlarını geri getirilemez şekilde imha eder.

* **📷 Otomatik Medya ve Belge Temizliği:**
  * **EXIF ve GPS Silme:** Gönderilen fotoğrafların kamera modeli, çekim saati, konum/GPS ve yazılım metaverilerini temizler.
  * **Belge Metaverisi Temizliği:** PDF dosyalarındaki yazar, oluşturucu ve cihaz bilgilerini arındırır.
  * **Görsel Ön Denetim:** Fotoğraf göndermeden önce ekranda güvenlik kontrol penceresi açarak arka plan detaylarının incelenmesini sağlar.

* **⚡ Motor ve Sohbet Yönetimi:**
  * **Çoklu Bot Desteği:** Birden fazla bot belirtecini eşzamanlı ve bağımsız iş parçacıklarında çalıştırır.
  * **Spam ve Sel Koruması:** Kayan zaman pencereli hız sınırlayıcı, yinelenen mesaj tespiti ve geçici engelleme kalkanı.
  * **Şifreli Yerel Depolama:** Sohbet notları, sabitleme ve mesaj geçmişini içeren thread-safe SQLite altyapısı.

### Proje Yapısı

```
UmbraGram/
├── main.py                   # PyQt6 masaüstü uygulaması ve arayüz
├── network_manager.py        # Tor kontrolcüsü, proxy havuzu ve jitter
├── text_neutralizer.py       # Kural tabanlı stilometri nötralizasyon motoru
├── shredder.py               # Donanıma duyarlı adli veri imha modülü
├── telegram_service.py       # Telegram Bot API arka plan işçileri ve medya temizleyici
├── db_manager.py             # SQLite veritabanı yöneticisi
├── spam_protector.py         # Hız sınırlayıcı ve spam koruma motoru
├── tests/                    # Birim ve entegrasyon testleri
├── requirements.txt          # Python bağımlılık listesi
└── run.bat                   # Hızlı başlatma betiği
```

### Kurulum ve Çalıştırma

1. **Depoyu klonlayın:**
   ```bash
   git clone https://github.com/CyberTarkan/UmbraGram.git
   cd UmbraGram
   ```

2. **Sanal ortam oluşturun ve aktif edin:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Bağımlılıkları yükleyin:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Uygulamayı başlatın:**
   ```bash
   python main.py
   ```

### Testleri Çalıştırma

```bash
pytest tests/ -v
```

### Hukuki Sorumluluk Reddi

> [!WARNING]
> Bu yazılım yalnızca eğitim, akademik araştırma ve yetkili güvenlik denetimi amaçlarıyla geliştirilmiştir. Yazılımın geliştiricileri ve katkıda bulunanlar; bu aracın kötüye kullanımından, yasa dışı faaliyetlerde kullanılmasından veya üçüncü taraf hizmet şartlarının (Telegram Hizmet Şartları dahil) ihlal edilmesinden kaynaklanabilecek doğrudan veya dolaylı hiçbir hukuki veya cezai **sorumluluk kabul etmez**. Yazılımı kullanan kişi, gerçekleştirdiği tüm eylemlerden ve yürürlükteki kanunlara uyumdan tamamen kendisi sorumludur.

---

## License / Lisans

Distributed under the [MIT License](LICENSE).
