# UmbraGram

<p align="center">
  <a href="#english">English</a> •
  <a href="#türkçe">Türkçe</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/GUI-PyQt6-green.svg" alt="PyQt6">
  <img src="https://img.shields.io/badge/Network-Tor%20SOCKS5-purple.svg" alt="Tor">
  <img src="https://img.shields.io/badge/Tests-305%20Passed-brightgreen.svg" alt="Tests">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

---

<a name="english"></a>
## English

**UmbraGram** is a security-hardened, privacy-centric desktop Telegram bot workstation built with Python and PyQt6. Designed for operational privacy, network traffic obfuscation, and anti-forensics, it combines network layer isolation with hardware-aware data sanitization and linguistic stylometry defense.

---

### How It Works (Architecture & Data Flow)

```
[User Input] ──► [TextNeutralizer (Stylometry)] ──► [Metadata Stripper (EXIF/GPS Clean)]
                                                              │
                                                              ▼
[Encrypted SQLite Vault] ◄── [SendActionWorker] ◄── [Packet Jitter (CSPRNG Delay)]
                                                              │
                                                              ▼
                                               [Tor / Proxy Circuit (SOCKS5)]
                                                              │
                                                      (Kill-Switch Guard)
                                                              │
                                                              ▼
                                                   [Telegram Bot API]
```

1. **Vault Initialization & Master Password:**
   * Upon startup, the user defines or enters a master password.
   * Key derivation initializes the local SQLite database in thread-safe Write-Ahead Logging (`WAL`) mode with cryptographic isolation.

2. **Network Shield & Traffic Obfuscation:**
   * **Tor & Proxy Chaining:** Automatically detects local `tor.exe` instances, executes them headlessly, and establishes an isolated SOCKS5 circuit on `127.0.0.1:9050` or dynamic elite proxy pool.
   * **Fail-Closed Kill Switch:** If the proxy tunnel or Tor circuit drops, all outbound worker threads are frozen in sub-millisecond time (<0.1ms), ensuring 0 bytes leak over the physical network interface.
   * **Timing Jitter:** Every outbound packet receives a non-deterministic, cryptographically randomized delay (`CSPRNG`) between configured thresholds to defeat ISP-level traffic timing correlation attacks.

3. **Message Preparation & Linguistic Stylometry Defense:**
   * **Stylometric Neutralization:** Before dispatching, messages pass through `TextNeutralizer`. It eliminates colloquialisms, texting abbreviations, vowel elongations (`selaaamm` $\to$ `selam`), vocative slang, profanity, and idiosyncratic casing while preserving URLs and emojis.
   * **Media De-identification:** Outgoing images, PDFs, and audio files are stripped of camera models, GPS coordinates, author tags, and software metadata before leaving the workstation.

4. **Hardware-Aware Forensic Sanitization:**
   * When data is removed or the emergency wipe shortcut (`Ctrl+Alt+Shift+X`) is triggered, the storage controller type is queried:
     * **NVMe / SSD:** Crypto-shredding destroys decryption keys first, followed by single-pass high-entropy overwrite and zero-byte truncation (`truncate(0)`) to signal OS-level TRIM deallocation, neutralizing Flash Translation Layer (FTL) wear-leveling remnants.
     * **Magnetic HDD:** Executes 3-pass DoD 5220.22-M overwrite patterns combined with hardware cache flushes (`os.fsync`).

---

### Key Features

* **🛡️ Network Shield:** Tor Onion routing, dynamic proxy pooling, sub-millisecond kill-switch, and CSPRNG packet jitter.
* **🧹 Text Neutralizer:** Rule-based linguistic stylometry defense stripping distinctive personal writing traits.
* **💽 Hardware-Aware Shredder:** Differentiated SSD TRIM and HDD DoD magnetic forensic destruction.
* **📷 Media Sanitizer:** Automated removal of EXIF, GPS, camera, and document metadata.
* **⚡ Multi-Bot Engine:** Multi-token concurrent polling with sliding-window anti-spam and flood rate-limiting.

---

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
   *(Or download the standalone `UmbraGram.exe` from [Releases](https://github.com/CyberTarkan/UmbraGram/releases))*

---

### Running Tests

UmbraGram includes an automated test suite verifying network resilience, stylometry, SQLite WAL concurrency, and UI flows:

```bash
pytest tests/ -v
```

---

### Disclaimer & Terms of Use

> [!WARNING]
> This software is provided strictly for educational, defensive research, and authorized security auditing purposes. The developers and contributors accept **no responsibility or liability** for any direct or indirect damage, misuse, illegal activities, or violations of third-party Terms of Service resulting from the use of this software. Users are solely responsible for ensuring compliance with applicable laws.

---

<a name="türkçe"></a>
## Türkçe

**UmbraGram**, Python ve PyQt6 ile geliştirilmiş, güvenlik ve mahremiyet odaklı masaüstü Telegram bot istemcisidir. Operasyonel gizlilik, ağ trafiğini gizleme ve adli bilişime karşı koyma (anti-forensics) araştırmaları için tasarlanmış olup; ağ katmanı izolasyonunu, donanıma duyarlı veri imhasını ve dilbilimsel stilometri (üslup) savunmasını tek çatı altında birleştirir.

---

### Çalışma Mantığı (Mimari ve Veri Akışı)

```
[Kullanıcı Girişi] ──► [Metin Nötralizasyonu (Stilometri)] ──► [Metaveri Temizliği (EXIF/GPS Silme)]
                                                                          │
                                                                          ▼
[Şifreli SQLite Kasası] ◄── [SendActionWorker] ◄── [Paket Jitter'ı (CSPRNG Gecikme)]
                                                                          │
                                                                          ▼
                                                       [Tor / Proxy Devresi (SOCKS5)]
                                                                          │
                                                                  (Kill-Switch Kalkanı)
                                                                          │
                                                                          ▼
                                                               [Telegram Bot API]
```

1. **Kasa Başlatma ve Ana Şifre:**
   * Program açıldığında ana şifre girilir.
   * Şifreleme anahtarı türetilerek yerel SQLite veritabanı eşzamanlı çalışmaya uygun Write-Ahead Logging (`WAL`) modunda güvenle açılır.

2. **Ağ Kalkanı ve Trafik Gizleme:**
   * **Tor & Proxy Tünellemesi:** Sistemdeki `tor.exe` dosyasını otomatik tespit eder ve arka planda sessizce başlatarak `127.0.0.1:9050` üzerinden izole SOCKS5 devresi veya dinamik proxy havuzu kurar.
   * **Acil Şalter (Kill-Switch):** Tünel veya Tor bağlantısı koptuğunda, tüm veri çıkış iş parçacıkları milisaniyenin altında (<0.1ms) dondurulur; fiziksel internet kartından dışarı **0 bayt** veri sızması garanti edilir.
   * **Zaman Analizi Bozucu (Jitter):** Çıkış yapan her pakete işletim sistemi seviyesinde kriptografik rastgelelikle (`CSPRNG`) gecikme eklenir; böylece servis sağlayıcı düzeyindeki zaman korelasyonu (Timing Attack) analizleri bozulur.

3. **Mesaj Hazırlığı ve Dilbilimsel Stilometri Savunması:**
   * **Üslup Temizliği:** Gönderilen mesajlar `TextNeutralizer` motorundan geçer. Sokak dili, mesajlaşma kısaltmaları, harf uzatmaları (`selaaamm` $\to$ `selam`), hitaplar ve küfürler resmi/tarafsız Türkçeye dönüştürülürken URL ve emojiler korunur.
   * **Medya Metaveri Temizliği:** Fotoğraflardaki EXIF, GPS konumları, kamera modelleri ve PDF yazar bilgileri giden dosyadan fiziksel olarak kazınır.

4. **Donanıma Duyarlı Adli Veri İmhası:**
   * Bir veri silindiğinde veya acil imha kısayolu (`Ctrl+Alt+Shift+X`) tetiklendiğinde depolama türü sorgulanır:
     * **NVMe / SSD:** Flash belleğin Aşınma Dengeleme (Wear-Leveling) yapısına karşı önce şifreleme anahtarları silinir (Crypto-shredding), ardından tek geçiş yüksek entropili yazma ve sıfır bayt kırpma (`truncate(0)`) ile işletim sistemine TRIM sinyali gönderilir.
     * **Manyetik HDD:** Fiziksel sektörlerdeki manyetik izleri sıfırlamak için 3 geçişli DoD 5220.22-M deseni ve donanımsal önbellek boşaltma (`os.fsync`) uygulanır.

---

### Temel Özellikler

* **🛡️ Ağ Kalkanı:** Tor Onion yönlendirmesi, dinamik proxy havuzu, kill-switch ve CSPRNG paket geciktirme.
* **🧹 Metin Nötralizasyonu:** Kişiye özgü yazım alışkanlıklarını silen kural tabanlı stilometri motoru.
* **💽 Donanıma Duyarlı İmha:** SSD TRIM ve HDD DoD adli imha motoru.
* **📷 Medya Temizleyici:** Fotoğraf, PDF ve ses dosyalarından metaveri arındırma.
* **⚡ Çoklu Bot Motoru:** Çok iş parçacıklı bot polling'i, kayan pencereli spam ve sel koruması.

---

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
   *(Veya [Releases](https://github.com/CyberTarkan/UmbraGram/releases) bölümünden doğrudan `UmbraGram.exe` dosyasını indirin)*

---

### Testleri Çalıştırma

Projede ağ güvenliği, adli imha, SQLite eşzamanlılığı ve arayüz akışlarını denetleyen 305 adet otomatik test bulunur:

```bash
pytest tests/ -v
```

---

### Hukuki Sorumluluk Reddi

> [!WARNING]
> Bu yazılım yalnızca eğitim, akademik araştırma ve yetkili güvenlik denetimi amaçlarıyla geliştirilmiştir. Yazılımın geliştiricileri ve katkıda bulunanlar; bu aracın kötüye kullanımından veya üçüncü taraf hizmet şartlarının ihlal edilmesinden kaynaklanabilecek doğrudan veya dolaylı hiçbir hukuki veya cezai **sorumluluk kabul etmez**. Kullanıcı, gerçekleştirdiği eylemlerden tamamen kendisi sorumludur.

---

## License / Lisans

Distributed under the [MIT License](LICENSE).
