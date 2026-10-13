# AnonimTelegram

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://riverbankcomputing.com/software/pyqt/)
[![Tor](https://img.shields.io/badge/Network-Tor%20SOCKS5-purple.svg)](https://www.torproject.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AnonimTelegram** is a security-hardened, privacy-centric desktop Telegram bot workstation built with Python and PyQt6. Designed for research in operational privacy, network traffic obfuscation, and anti-forensics, it combines network layer isolation with hardware-aware data sanitization and linguistic stylometry defense.

---

## Key Features

### 🛡️ Network Shield & Traffic Obfuscation
* **Tor Onion Routing Integration:** Automated detection and background headless management of local `tor.exe` instances, establishing isolated SOCKS5 circuits on `127.0.0.1:9050`.
* **Dynamic Elite Proxy Chaining:** Multi-threaded verification of public and custom proxy pools (SOCKS5/HTTP) with automatic failover and latency tracking.
* **Fail-Closed Kill Switch:** Automatically severs all outbound network worker threads if the proxy tunnel or Tor circuit drops, preventing real IP leaks.
* **Microsecond Timing Jitter:** Injects non-deterministic, configurable millisecond delays into outgoing packets to defeat ISP-level traffic timing correlation attacks.

### 🧹 Linguistic Stylometry Neutralizer (`TextNeutralizer`)
* **Rule-Based Forensic Stylometry Defense:** Transforms distinctive conversational text into neutral, standardized formal language.
* **Dialect & Shorthand Elimination:** Strips Turkish SMS abbreviations, irregular vowel elongations (e.g., `selaaamm` $\to$ `selam`), vocative slang, profanities, and idiosyncratic punctuation.
* **Keyboard Shortcut:** Instant neutralization accessible via `Ctrl+Shift+N` or the inline `🪄` interface action.

### 💽 Hardware-Aware Forensic Sanitization (`shredder.py`)
* **Physical Architecture Detection:** Queries physical disk controllers to distinguish magnetic platters (HDD) from flash memory (NVMe/SSD).
* **HDD Mode:** Multi-pass DoD overwrite sequence (`os.urandom` + `0x00` + `0xFF`) accompanied by low-level `os.fsync` flushes to neutralize magnetic remnant traces.
* **NVMe / SSD Mode:** Applies high-entropy single-pass overwrite combined with zero-byte truncation (`truncate(0)`) to signal OS-level TRIM deallocation, mitigating Flash Translation Layer (FTL) wear-leveling data remnants.
* **Emergency Self-Destruct:** One-touch cryptographic key erasure and database wipe triggered via `Ctrl+Alt+Shift+X`.

### 📷 Automated Media & Document De-identification
* **EXIF & GPS Stripping:** Strips camera metadata, GPS coordinates, device identifiers, and editing software headers from outgoing images.
* **Document Scrubbing:** Cleans PDF author, producer, and creation date fields prior to upload.
* **Pre-Flight Visual Inspection:** Displays a security verification prompt before dispatching images.

### ⚡ Engine & Chat Management
* **Multi-Bot Orchestration:** Concurrent polling across multiple bot tokens with isolated session threads.
* **Spam & Flooding Protection:** Adaptive rate limiting with sliding-window tracking, identical message throttling, and temporary cooldown locks.
* **Encrypted Local Storage:** Thread-safe SQLite database schema supporting custom notes, pinning, and full conversation removal.

---

## Project Structure

```
AnonimTelegram/
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

---

## Installation

### Prerequisites
* **Python 3.10+** (64-bit recommended)
* Optional: **Tor Browser** or standalone **Tor Expert Bundle** installed locally for Tor Onion routing capabilities.

### Setup
1. Clone this repository:
   ```bash
   git clone https://github.com/CyberTarkan/AnonimTelegram.git
   cd AnonimTelegram
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Launch the application:
   ```bash
   python main.py
   ```
   *(On Windows, you can also double-click `run.bat`)*

---

## Running Tests

The test suite covers database operations, network shield failovers, stylometric transformations, and forensic shredding:

```bash
pytest tests/ -v
```

---

## Operational Security (OpSec) Best Practices

For users requiring strict operational anonymity against advanced forensic auditing, refer to the [ANONYMITY_GUIDE.md](ANONYMITY_GUIDE.md) document detailing:
* Operating system isolation (Tails OS and Whonix deployments).
* Full Disk Encryption (FDE) and cold-boot attack mitigation.
* Safe acquisition of communication tokens and numbers.

---

## Disclaimer & Terms of Use / Sorumluluk Reddi

> [!WARNING]
> **ENGLISH:** This software is provided strictly for educational, defensive research, and authorized security auditing purposes. The developers, contributors, and maintainers accept **no responsibility or liability** for any direct or indirect damage, misuse, illegal activities, or violations of third-party Terms of Service (including Telegram's Terms of Service) resulting from the use of this software. End users are solely responsible for ensuring that their deployment complies with all applicable local, national, and international laws and regulations.
>
> **TÜRKÇE:** Bu yazılım yalnızca eğitim, akademik araştırma ve meşru güvenlik denetimi amaçlarıyla geliştirilmiştir. Yazılımın geliştiricileri ve katkıda bulunanlar; bu aracın kötüye kullanımından, yasa dışı faaliyetlerde kullanılmasından veya üçüncü taraf hizmet şartlarının (Telegram Hizmet Şartları dahil) ihlal edilmesinden kaynaklanabilecek doğrudan veya dolaylı hiçbir hukuki veya cezai **sorumluluk kabul etmez**. Yazılımı kullanan kişi, gerçekleştirdiği tüm eylemlerden ve yürürlükteki kanunlara uyumdan tamamen kendisi sorumludur.

---

## License

Distributed under the [MIT License](LICENSE).
