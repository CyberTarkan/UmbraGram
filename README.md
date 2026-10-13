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
UmbraGram is a security-hardened desktop messaging client that allows you to chat with people through a Telegram bot without ever revealing your personal phone number, real identity, IP address, or unique writing habits.

---

### How It Works

* **Conversations Through Your Bot:** Instead of chatting from a personal Telegram account, you connect your Telegram bot token to UmbraGram. Other people message your bot directly from their standard Telegram app. Their messages instantly appear in your desktop client, allowing you to reply in real time as the bot. Users only see and interact with your bot; your personal account, phone number, and contacts remain completely unexposed.
* **Network & IP Protection:** All data transfer between your computer and Telegram's servers is routed through an isolated Tor SOCKS5 circuit (`127.0.0.1:9050`) or an elite proxy. If the secure tunnel drops, an automated Kill-Switch instantly freezes outgoing network traffic in less than 0.1 milliseconds, ensuring your real home or office IP address is never leaked. Additionally, random millisecond delays (Jitter) are applied to outbound packets to defeat timing correlation tracking by internet service providers.
* **Writing Style & Identity Scrubbing:** When you type a message, the built-in neutralizer (`Ctrl+Shift+N`) standardizes your text before it is sent. It removes distinctive slang, profanities, texting abbreviations, and vowel elongations (converting phrases like `selaaamm` to `selam`) so your personal writing habits cannot be forensically profiled.
* **Automatic File & Photo Cleaning:** When you send images, documents, or audio files through the bot, the client automatically wipes all embedded EXIF tags, GPS location coordinates, camera models, and author metadata.
* **Hardware-Aware Data Destruction:** When a conversation is deleted or the emergency wipe shortcut (`Ctrl+Alt+Shift+X`) is pressed, UmbraGram checks your physical drive type: it runs cryptographic key shredding and TRIM deallocation on NVMe/SSDs to prevent Flash Translation Layer remnants, and multi-pass magnetic overwriting (DoD 5220.22-M) on magnetic HDDs.

---

### Key Features

* **Bot-Based Workstation:** Chat with multiple people through your bot tokens in a familiar, modern desktop interface.
* **Tor & Proxy Shield:** SOCKS5 tunneling, automated local Tor process management, and fail-closed kill-switch.
* **Text Neutralizer:** Rule-based Turkish stylometry engine removing personal writing signatures.
* **Media Sanitizer:** Strips GPS, camera metadata, and document author headers before upload.
* **Hardware-Aware Shredder:** Differentiated forensic sanitization for SSD and HDD drives.
* **Multi-Bot Engine:** Concurrently manage multiple bot tokens with built-in anti-spam flood protection.

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
UmbraGram, kişisel telefon numaranızı, gerçek kimliğinizi, IP adresinizi veya yazım tarzınızı açık etmeden bir Telegram botu üzerinden insanlarla sohbet etmenizi sağlayan masaüstü bir mesajlaşma istemcisidir.

---

### Nasıl Çalışır?

* **Bot Aracılığıyla Sohbet:** Kişisel bir Telegram hesabından yazışmak yerine, oluşturduğunuz botun belirtecini (token) UmbraGram'a eklersiniz. Karşıdaki kişiler normal Telegram uygulamalarından botunuza mesaj yazar. Gelen mesajlar doğrudan masaüstü ekranınızdaki sohbet penceresine düşer ve siz de karşı tarafa botun arkasından canlı olarak yanıt verirsiniz. Karşı taraf yalnızca botla konuştuğunu görür; kişisel profiliniz, telefon numaranız veya rehberiniz hiçbir şekilde paylaşılmaz.
* **Ağ ve IP Koruması:** Bilgisayarınız ile Telegram sunucuları arasındaki tüm iletişim izole bir Tor SOCKS5 devresi (`127.0.0.1:9050`) veya proxy üzerinden yürütülür. Güvenli bağlantı kopsa dahi acil durum şalteri (Kill-Switch) milisaniyenin altında bir sürede tüm giden trafiği dondurarak gerçek IP adresinizin dışarı sızmasını kesin olarak engeller. Ayrıca giden paketlere eklenen mikro gecikmeler (Jitter) sayesinde internet servis sağlayıcısının zaman analizi yapması zorlaştırılır.
* **Üslup ve Yazı Stili Temizliği:** Mesajınızı yazıp göndermeden önce nötralizasyon motoru (`Ctrl+Shift+N`) kişisel yazım alışkanlıklarınızı temizler. Argo ifadeler, sokak jargonu, mesajlaşma kısaltmaları ve harf uzatmaları (örneğin `selaaamm` yerine `selam`) standart resmi dile dönüştürülür; böylece yazım üslubunuz üzerinden kimlik tespiti yapılamaz.
* **Görsel ve Dosya Metaveri Temizliği:** Bot üzerinden fotoğraf, PDF veya ses dosyası gönderdiğinizde, dosyanın içine gizlenmiş GPS konum koordinatları, kamera modeli, çekim saati ve yazar bilgileri otomatik olarak silinir.
* **Donanıma Duyarlı Adli İmha:** Bir sohbet silindiğinde veya acil imha kısayolu (`Ctrl+Alt+Shift+X`) tetiklendiğinde depolama türü denetlenir: NVMe/SSD sürücülerde şifreleme anahtarları imha edilip TRIM komutu tetiklenerek veri kalıntıları engellenir, manyetik HDD'lerde ise 3 geçişli manyetik üzerine yazma (DoD) uygulanır.

---

### Temel Özellikler

* **Bot Tabanlı İletişim:** Bot tokeni ile bağlanıp insanlarla normal bir Telegram uygulaması gibi birebir yazışma.
* **Tor & Proxy Kalkanı:** SOCKS5 tünellemesi, otomatik Tor yönetimi ve sızıntı önleyici Kill-Switch.
* **Metin Nötralizasyonu:** Kişiye özgü konuşma tarzını, argo ve kısaltmaları silen Türkçe stilometri motoru.
* **Medya Temizleyici:** Fotoğraf ve belgelerden konum/kamera metaverilerini kaldırma.
* **Donanıma Duyarlı İmha:** SSD ve HDD sürücüler için adli bilişime karşı özel imha algoritmaları.
* **Çoklu Bot Yönetimi:** Birden fazla botu aynı anda yönetme ve otomatik spam/sel engelleme.

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
