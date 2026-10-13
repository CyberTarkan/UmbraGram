# Anonim İletişim ve Operasyonel Güvenlik (OpSec) Rehberi

Bu belge, `AnonimTelegram` istemcisi kullanılırken adli bilişim, ağ izleme ve servis sağlayıcı seviyesindeki tehdit modellerine karşı tam anonimliği korumak için uyulması gereken temel ilkeleri içerir.

---

## 1. İşletim Sistemi ve Donanım Katmanı
* **Tails OS veya Whonix Tercihi:** Standart Windows işletim sistemi; Event Log, Prefetch, Amcache ve SRUM veritabanlarında çalıştırılan programların ve ağ transferlerinin kaydını tutar. Adli bilişim incelemelerinde diske iz bırakmamak için uygulamanın doğrudan RAM üzerinde çalışan **Tails OS** (Canlı USB) veya çift katmanlı **Whonix** sanal makinesinde çalıştırılması esastır.
* **Tam Disk Şifrelemesi (FDE):** Cihaz kapatıldığında adli kopyalama (disk image) işlemlerini engellemek için tüm diskler VeraCrypt, BitLocker veya LUKS ile şifrelenmelidir.
* **Bellek (RAM) Güvenliği:** Bilgisayar çalışır durumdayken el konulması halinde RAM dökümünden (Memory Dump) oturum anahtarları okunabilir. Risk durumunda anında güç kesme veya Tails USB'sini çekme prosedürü uygulanmalıdır.

---

## 2. Numara ve Hesap Edinimi
* **Kişisel Kimlik Ayrımı:** Telegram hesabı veya bot kesinlikle kişisel bir telefon numarası veya SIM kart ile oluşturulmamalıdır.
* **Ödeme İzleri:** Sanal numara satın alırken kredi kartı, banka havalesi veya KYC (kimlik doğrulamalı) borsa cüzdanları kullanılmamalıdır. Yalnızca iz sürülemez kripto varlıklar (Monero - XMR) veya temiz kuponlar kullanılmalıdır.
* **Sosyal İzolasyon:** Anonim hesap üzerinden kişisel tanıdıklarla, aileyle veya gerçek kimliğin bilindiği gruplarla hiçbir temas kurulmamalıdır.

---

## 3. Ağ ve Trafik Güvenliği
* **Tor ve Kill-Switch Zorunluluğu:** Uygulama başlatılırken `Tor + Proxy` kalkanı ve `Kill-Switch` asla devre dışı bırakılmamalıdır. Bağlantı kesilirse gerçek IP sızıntısı anında engellenir.
* **Zaman Korelasyonuna Karşı Jitter:** İSS düzeyinde mesaj gönderme anları ile Tor paket çıkışlarının eşleştirilmesini (Timing Attack) önlemek için Ayarlar bölümünden `Paket Gecikmesi (Jitter)` açık tutulmalıdır.
* **İSS Ayrımı:** Ev veya iş yeri gibi aboneliği adınıza kayıtlı internet hatları yerine, Tor trafiğinin dikkat çekmeyeceği izole veya kamuya açık ağlar tercih edilmelidir.

---

## 4. İletişim ve Üslup (Stilometri) Disiplini
* **Metin Nötralizasyonu:** Kişisel yazım tarzı, imla hataları, sık kullanılan argo kelimeler ve noktalama alışkanlıkları adli dilbilim (forensic stylometry) araçlarıyla analiz edilebilir. Mesaj yazıldıktan sonra mutlaka `🪄 Nötralize Et` butonu veya `Ctrl+Shift+N` kısayolu kullanılmalıdır.
* **Görsel ve Medya Kontrolü:** Gönderilen fotoğraflarda EXIF/GPS metaverileri temizlense bile görselin arka planındaki yansımalar, konum ipuçları veya cihaz arayüzleri incelenmelidir. Gönderim öncesi açılan güvenlik onay penceresi dikkatle kontrol edilmelidir.
* **Zaman Çizelgesi Dağıtımı:** Belirli ve düzenli saatlerde (örneğin her gün aynı saat aralığında) çevrimiçi olmak, şüphelinin günlük yaşam ritmiyle örtüşme oluşturabilir.

---

## 5. Acil Durum Protokolü
* Fiziksel denetim veya ani risk durumunda yapılandırılan acil durum kısayolu (`Ctrl+Alt+Shift+X`) veya arayüzdeki `🚨 Acil İmha` butonu kullanılmalıdır.
* SSD/NVMe sürücülerde güvenli silme sonrasında sistem seviyesinde TRIM sinyali tetiklenerek flash hücrelerinin deallocate edilmesi sağlanır.
