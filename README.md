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

### What is UmbraGram?
**UmbraGram** is a desktop workstation that allows you to chat with people through a Telegram bot without ever revealing your personal phone number, real identity, IP address, or unique writing style. 

Instead of messaging from a personal account, you connect your Telegram bot token to UmbraGram. When users send messages to your bot, they appear in your desktop client just like a normal chat app, and you can reply to them in real time behind a multi-layered shield of anonymity.

```
[Other Users] ──(Telegram App)──► [Your Bot] ──(Tor / SOCKS5)──► [UmbraGram Desktop Client (You)]
```

---

### How It Works (Under the Hood)

1. **Bot-Mediated Conversations:**
   * You create or use a Telegram bot token. Users only see and talk to the bot. Your personal Telegram account, contact list, and phone number are never involved or exposed.
2. **Network Shield (Tor & Proxy):**
   * All polling and message dispatches pass through an isolated Tor SOCKS5 circuit (`127.0.0.1:9050`) or elite proxy.
   * If the connection fails, an automatic **Kill-Switch** halts all outbound traffic in under 0.1ms to prevent real IP leaks.
   * Random millisecond delays (**Jitter**) are injected into outgoing packets to defeat network timing correlation attacks.
3. **Linguistic Stylometry Neutralizer:**
   * Before you send a message, the built-in `🪄` neutralizer cleans your typing habits: slang, profanity, dialectal spellings, and repeated characters (`selaaamm` $\to$ `selam`) are standardized so your writing style cannot be forensically profiled.
4. **Metadata Stripping:**
   * Photos, documents, and audio files sent through the bot have their EXIF, GPS location coordinates, camera models, and author tags automatically wiped.
5. **Hardware-Aware Data Destruction:**
   * When messages are deleted or the emergency wipe shortcut (`Ctrl+Alt+Shift+X`) is triggered, UmbraGram executes DoD multi-pass overwrites for HDDs and Crypto-shredding + TRIM deallocation for NVMe/SSDs.

---

### Key Features

* **🤖 Bot-Based Workstation:** Chat with multiple people through your bot tokens in a familiar, modern desktop interface.
* **🛡️ Tor & Proxy Shield:** SOCKS5 tunneling, automated local Tor process management, and fail-closed kill-switch.
* **🧹 Text Neutralizer:** Rule-based Turkish stylometry engine removing personal writing signatures.
* **📷 Media Sanitizer:** Strips GPS, camera metadata, and document author headers before upload.
* **💽 Hardware-Aware Shredder:** Differentiated forensic sanitization for SSD and HDD drives.
* **⚡ Multi-Bot Engine:** Concurrently manage multiple bot tokens with built-in anti-spam flood protection.

---

### Installation & Usage

1. **Clone the repository:**
   ```bash
   git clone https://github.com/CyberTarkan/UmbraGram.git
   cd UmbraGram
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python main.py
   ```
   *(Or download the pre-compiled `UmbraGram.exe` from [Releases](https://github.com/CyberTarkan/UmbraGram/releases))*

---

### Running Tests

```bash
pytest tests/ -v
```

---

### Disclaimer & Terms of Use

> [!WARNING]
> This software is provided strictly for educational, defensive research, and authorized security auditing purposes. The developers and contributors accept **no responsibility or liability** for any misuse, illegal activities, or violations of third-party Terms of Service resulting from the use of this software.

---

<a name="türkçe"></a>
## Türkçe

### UmbraGram Nedir?
**UmbraGram**, kişisel telefon numaranızı, gerçek kimliğinizi, IP adresinizi veya yazım tarzınızı açık etmeden **bir Telegram botu üzerinden insanlarla sohbet etmenizi sağlayan** masaüstü bir mesajlaşma istemcisidir.

Kişisel bir hesaptan yazışmak yerine, oluşturduğunuz botun belirtecini (token) UmbraGram'a eklersiniz. İnsanlar botunuza mesaj attığında, bu mesajlar tıpkı normal bir sohbet programı gibi masaüstü ekranınıza düşer. Siz de karşı tarafa botun arkasından canlı olarak yanıt verirsiniz.

```
[Diğer Kullanıcılar] ──(Telegram)──► [Botunuz] ──(Tor / SOCKS5 Kalkanı)──► [UmbraGram Masaüstü (Siz)]
```

---

### Nasıl Çalışır? (Adım Adım)

1. **Bot Aracılığıyla Sohbet:**
   * Karşıdaki kişi sadece botu görür ve botla konuşur. Kişisel Telegram profiliniz, rehberiniz ve telefon numaranız hiçbir şekilde devreye girmez.
2. **Ağ Kalkanı (Tor & Proxy):**
   * Botun tüm veri trafiği izole bir Tor SOCKS5 devresi (`127.0.0.1:9050`) veya proxy üzerinden akar.
   * Bağlantı aniden kopsa bile **Kill-Switch** sistemi 0.1 milisaniyeden kısa sürede trafiği dondurarak gerçek ev/iş IP adresinizin sızmasını engeller.
   * Çıkış yapan mesajlara milisaniye seviyesinde rastgele gecikmeler (**Jitter**) eklenerek İSS düzeyindeki zaman eşleştirme analizleri bozulur.
3. **Üslup ve Yazı Stili Temizliği (Stilometri):**
   * Mesaj yazarken `🪄` butonuna (`Ctrl+Shift+N`) bastığınızda; kullandığınız argo kelimeler, konuşma dili kısaltmaları ve harf uzatmaları (`selaaam` $\to$ `selam`) standart resmi Türkçeye dönüştürülür. Böylece yazım tarzınızdan kimlik tespiti yapılamaz.
4. **Görsel ve Dosya Metaveri Temizliği:**
   * Gönderdiğiniz fotoğraflardaki GPS konumları, çekim saati, kamera modeli ve PDF yazar bilgileri otomatik olarak silinir.
5. **Donanıma Duyarlı Adli İmha:**
   * Bir sohbet silindiğinde veya acil imha kısayolu (`Ctrl+Alt+Shift+X`) tetiklendiğinde; SSD'lerde Crypto-shredding ve TRIM, HDD'lerde ise 3 geçişli manyetik üzerine yazma (DoD) ile diskteki kalıntılar sıfırlanır.

---

### Temel Özellikler

* **🤖 Bot Tabanlı İletişim:** Bot tokeni ile bağlanıp insanlarla normal bir Telegram uygulaması gibi birebir yazışma.
* **🛡️ Tor & Proxy Kalkanı:** SOCKS5 tünellemesi, otomatik Tor yönetimi ve sızıntı önleyici Kill-Switch.
* **🧹 Metin Nötralizasyonu:** Kişiye özgü konuşma tarzını, argo ve kısaltmaları silen Türkçe stilometri motoru.
* **📷 Medya Temizleyici:** Fotoğraf ve belgelerden konum/kamera metaverilerini kaldırma.
* **💽 Donanıma Duyarlı İmha:** SSD ve HDD sürücüler için adli bilişime karşı özel imha algoritmaları.
* **⚡ Çoklu Bot Yönetimi:** Birden fazla botu aynı anda yönetme ve otomatik spam/sel engelleme.

---

### Kurulum ve Çalıştırma

1. **Depoyu klonlayın:**
   ```bash
   git clone https://github.com/CyberTarkan/UmbraGram.git
   cd UmbraGram
   ```

2. **Bağımlılıkları yükleyin:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Uygulamayı başlatın:**
   ```bash
   python main.py
   ```
   *(Veya [Releases](https://github.com/CyberTarkan/UmbraGram/releases) bölümünden doğrudan `UmbraGram.exe` dosyasını indirin)*

---

### Testleri Çalıştırma

```bash
pytest tests/ -v
```

---

### Hukuki Sorumluluk Reddi

> [!WARNING]
> Bu yazılım yalnızca eğitim, akademik araştırma ve yetkili güvenlik denetimi amaçlarıyla geliştirilmiştir. Yazılımın geliştiricileri ve katkıda bulunanlar; bu aracın kötüye kullanımından veya üçüncü taraf hizmet şartlarının ihlal edilmesinden kaynaklanabilecek doğrudan veya dolaylı hiçbir hukuki veya cezai **sorumluluk kabul etmez**.

---

## License / Lisans

Distributed under the [MIT License](LICENSE).
