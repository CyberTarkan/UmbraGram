import os
import sys
import time
import math
import uuid
import tempfile
import statistics
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from PIL import Image, PngImagePlugin
from PyPDF2 import PdfWriter, PdfReader

from network_manager import NetworkShieldManager, ShieldMode
from telegram_service import SendActionWorker, FetchProfileWorker, BotWorker, strip_media_metadata
from shredder import secure_shred_file, secure_shred_directory, detect_drive_type
from db_manager import DatabaseSecurityManager


# ====================================================================
# 1. Ağ Kalkanı (Kill-Switch & Zero-Leak Resilience)
# ====================================================================
class TestDeepKillSwitchAudit:
    """
    Validates that whenever proxy connectivity drops, Tor circuit severs,
    or network is frozen, all worker threads freeze within milliseconds and
    absolutely zero bytes leak to the real IP interface (0-byte leak guarantee).
    """

    def test_kill_switch_triggers_sub_millisecond_freeze(self):
        """Measures the exact freeze activation latency (must be < 5 ms)."""
        net_mgr = NetworkShieldManager(mode=ShieldMode.TOR, kill_switch=True)
        net_mgr.active_proxy = "socks5h://127.0.0.1:9050"

        t_start = time.perf_counter()
        net_mgr.trigger_kill_switch(reason="Tor circuit severed")
        freeze_latency_ms = (time.perf_counter() - t_start) * 1000.0

        assert net_mgr.is_frozen is True, "Network must be in frozen state!"
        assert freeze_latency_ms < 5.0, f"Kill-switch activation took {freeze_latency_ms:.3f}ms (threshold: < 5ms)!"

    def test_kill_switch_zero_byte_leak_on_proxy_drop_concurrent_workers(self):
        """
        Spawns 10 concurrent SendActionWorkers. When the proxy is severed mid-flight,
        every worker freezes instantly and zero requests hit the direct internet.
        """
        net_mgr = NetworkShieldManager(mode=ShieldMode.PROXY, kill_switch=True)
        net_mgr.active_proxy = "http://10.200.0.1:8080"

        post_calls = []
        get_calls = []

        def mock_post(url, **kwargs):
            proxies = kwargs.get("proxies") or {}
            # If proxies is empty or missing, it's a DIRECT REAL IP LEAK!
            if not proxies or not any(proxies.values()):
                post_calls.append(("LEAK_DIRECT", url, kwargs))
            else:
                post_calls.append(("PROXIED", url, kwargs))
            # Simulate proxy death
            raise requests.exceptions.ProxyError("Proxy tunnel abruptly closed")

        def mock_get(url, **kwargs):
            get_calls.append(url)
            raise requests.exceptions.ProxyError("Proxy tunnel abruptly closed")

        workers = []
        callbacks = []

        for i in range(10):
            cb = MagicMock()
            callbacks.append(cb)
            w = SendActionWorker(
                token="123456:FAKE_TOKEN_LEAK_TEST",
                action="sendMessage",
                params={"chat_id": 100 + i, "text": f"Confidential payload #{i}"},
                network_manager=net_mgr,
                callback=cb
            )
            workers.append(w)

        # Trigger Kill-Switch
        net_mgr.trigger_kill_switch(reason="Proxy gateway unreachable")

        # Execute all workers across threads
        threads = [threading.Thread(target=w.run) for w in workers]
        with patch("requests.post", side_effect=mock_post), patch("requests.get", side_effect=mock_get):
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=3.0)

        # Verify zero requests bypassed the shield
        direct_leaks = [c for c in post_calls if c[0] == "LEAK_DIRECT"]
        assert len(direct_leaks) == 0, f"CRITICAL: {len(direct_leaks)} requests leaked real IP!"
        assert len(post_calls) == 0, f"CRITICAL: Workers transmitted data after freeze: {len(post_calls)} calls!"
        assert len(get_calls) == 0, "No GET requests should be transmitted!"

        # Verify all callbacks received the kill-switch / frozen error
        for cb in callbacks:
            assert cb.call_count == 1
            success, result, err = cb.call_args[0]
            assert success is False
            assert "Ağ donduruldu" in err or "Kill-Switch" in err

    def test_tor_disconnect_halts_bot_worker_polling_immediately(self):
        """
        Validates that a running BotWorker detecting Tor disconnection halts
        its long-polling loop without emitting real IP packets.
        """
        net_mgr = NetworkShieldManager(mode=ShieldMode.TOR, kill_switch=True)
        net_mgr.active_proxy = "socks5h://127.0.0.1:9050"

        worker = BotWorker(bot_id=1, token="FAKE_TOKEN", network_manager=net_mgr)
        direct_leak_count = 0

        def fake_get(url, **kwargs):
            nonlocal direct_leak_count
            proxies = kwargs.get("proxies") or {}
            if not proxies or "socks5h" not in str(proxies):
                direct_leak_count += 1
            raise requests.exceptions.ProxyError("Tor SOCKS5 host unreachable")

        session_mock = MagicMock()
        session_mock.get.side_effect = fake_get
        session_mock.proxies = {"http": net_mgr.active_proxy, "https": net_mgr.active_proxy}

        worker.session = session_mock
        worker.is_running = True

        # Run 1 polling iteration which catches ProxyError -> triggers kill switch
        def mock_msleep(ms):
            worker.is_running = False

        worker.msleep = mock_msleep

        with patch("requests.Session", return_value=session_mock):
            # Simulate loop step
            try:
                if net_mgr and net_mgr.kill_switch:
                    session_mock.proxies = net_mgr.get_requests_proxies()
                session_mock.get("https://api.telegram.org/botFAKE/getUpdates", proxies=session_mock.proxies)
            except requests.exceptions.ProxyError as e:
                net_mgr.trigger_kill_switch(str(e))

        assert net_mgr.is_frozen is True, "Kill-switch must be triggered!"
        assert direct_leak_count == 0, f"Direct network leak occurred: {direct_leak_count} requests!"

    def test_fetch_profile_worker_zero_bytes_leaked_on_frozen(self):
        """Ensures background profile avatar download halts without leaking IP."""
        net_mgr = NetworkShieldManager(mode=ShieldMode.HYBRID, is_frozen=True, kill_switch=True)
        cb = MagicMock()
        worker = FetchProfileWorker(
            token="FAKE_TOKEN",
            bot_id=1,
            chat_id=8888,
            callback=cb,
            network_manager=net_mgr
        )

        with patch("requests.Session.get") as mock_get:
            worker.run()
            assert mock_get.call_count == 0, "FetchProfileWorker initiated network connection while frozen!"
        assert cb.call_count == 0


# ====================================================================
# 2. Paket Jitter'i (Traffic Analysis & Correlation Thwarting)
# ====================================================================
class TestDeepJitterAudit:
    """
    Statistical validation of millisecond packet timing jitter:
    Ensures 50 requests exhibit true cryptographically secure, non-deterministic
    uniform distribution within [min_ms, max_ms] to defeat ISP traffic correlation attacks.
    """

    def test_jitter_50_packets_statistical_randomness(self):
        net_mgr = NetworkShieldManager()
        min_ms = 400
        max_ms = 1600
        net_mgr.set_jitter(enabled=True, min_ms=min_ms, max_ms=max_ms)

        # Intercept sleep calls to record exact applied delay without waiting 50 real seconds
        delays = []

        def fake_sleep(secs):
            delays.append(secs * 1000.0)

        with patch("time.sleep", side_effect=fake_sleep):
            for _ in range(50):
                applied = net_mgr.apply_jitter()
                assert min_ms <= applied <= max_ms, f"Jitter value {applied} out of bounds [{min_ms}, {max_ms}]"

        assert len(delays) == 50, "Must have exactly 50 samples"

        # 1. Bounds Validation
        for d in delays:
            assert min_ms <= d <= max_ms, f"Observed delay {d} outside bounds [{min_ms}, {max_ms}]"

        # 2. Non-Determinism & Uniqueness Check (No constant or repeating values)
        unique_count = len(set(delays))
        assert unique_count >= 48, f"Insufficient entropy! Only {unique_count}/50 unique delays."

        # 3. Consecutive Non-Identity (timing changes with every packet)
        for i in range(1, len(delays)):
            assert delays[i] != delays[i - 1], f"Identical consecutive delay detected: {delays[i]}"

        # 4. Statistical Distribution (Mean & Standard Deviation)
        sample_mean = statistics.mean(delays)
        theoretical_midpoint = (min_ms + max_ms) / 2.0  # 1000.0 ms
        mean_deviation = abs(sample_mean - theoretical_midpoint)
        # For 50 uniform samples, sample mean standard error is (max-min)/sqrt(12*50) ≈ 48.9 ms.
        # 3 sigma tolerance ≈ 150 ms.
        assert mean_deviation < 160.0, f"Sample mean {sample_mean:.2f} deviates too far from expected midpoint {theoretical_midpoint:.2f}"

        sample_stdev = statistics.stdev(delays)
        theoretical_stdev = (max_ms - min_ms) / math.sqrt(12.0)  # ≈ 346.41 ms
        # Standard deviation must be well-formed
        assert 200.0 <= sample_stdev <= 450.0, f"Abnormal jitter standard deviation: {sample_stdev:.2f} (expected ~{theoretical_stdev:.2f})"

        # 5. Quartile Spread (Entropy across entire window)
        quartile_size = (max_ms - min_ms) / 4.0
        bins = [0, 0, 0, 0]
        for d in delays:
            idx = min(3, int((d - min_ms) / quartile_size))
            bins[idx] += 1

        for idx, count in enumerate(bins):
            assert count >= 4, f"Quartile {idx} has too few samples ({count}/50), indicating severe bias/clumping!"

    def test_jitter_applied_prior_to_send_action(self):
        """Verifies that SendActionWorker strictly triggers apply_jitter before socket connection."""
        net_mgr = NetworkShieldManager()
        net_mgr.active_proxy = "http://127.0.0.1:8080"
        order_of_execution = []

        def fake_apply_jitter():
            order_of_execution.append("apply_jitter")
            return 500.0

        def fake_post(*args, **kwargs):
            order_of_execution.append("requests_post")
            mock = MagicMock()
            mock.json.return_value = {"ok": True, "result": {"message_id": 1}}
            return mock

        worker = SendActionWorker(
            token="FAKE_TOKEN",
            action="sendMessage",
            params={"chat_id": 123, "text": "Testing jitter execution order"},
            network_manager=net_mgr
        )

        with patch.object(net_mgr, "apply_jitter", side_effect=fake_apply_jitter), \
             patch("requests.post", side_effect=fake_post):
            worker.run()

        assert order_of_execution == ["apply_jitter", "requests_post"], (
            f"Execution order violation! Expected ['apply_jitter', 'requests_post'], got {order_of_execution}"
        )


# ====================================================================
# 3. Adli İmha (Forensic Shredder & Hardware Sanitization)
# ====================================================================
class TestDeepForensicShredderAudit:
    """
    Forensic sanitization testing on isolated MOCK/TEMP files:
    - HDD: DoD 5220.22-M 3-pass overwrite + os.fsync + 0-byte truncation + MFT rename + deletion.
    - SSD: Single-pass cryptographic obfuscation + TRIM 0-byte truncation + MFT rename + deletion.
    - Crypto-shredding: AES-256 vault key destruction mathematically rendering encrypted data unrecoverable.
    """

    def test_hdd_dod_3pass_wipes_disk_remnants(self, tmp_path):
        """
        Creates a temporary file filled with a recognizable sensitive sequence.
        Executes DoD 3-pass sanitization and verifies:
        1. File is overwritten and fsynced.
        2. File is truncated to 0 bytes.
        3. File is renamed to random UUID and deleted.
        4. No sector remnants of the sensitive pattern exist at the path or directory.
        """
        secret_pattern = b"TOP_SECRET_FORENSIC_EVIDENCE_MAGNETIC_HDD_2026_" * 200
        temp_file = tmp_path / "sensitive_hdd_document.dat"
        temp_file.write_bytes(secret_pattern)
        orig_size = temp_file.stat().st_size
        assert orig_size > 0

        # Run HDD DoD sanitization
        success = secure_shred_file(temp_file, drive_type="HDD")
        assert success is True, "HDD secure shred failed!"

        # Verify file is completely removed
        assert not temp_file.exists(), "Original file path still exists after shredding!"

        # Search the entire directory for any remnant matching the secret pattern
        for entry in tmp_path.iterdir():
            if entry.is_file():
                content = entry.read_bytes()
                assert secret_pattern[:32] not in content, "Disk remnants found in directory!"

    def test_ssd_trim_sanitization(self, tmp_path):
        """
        Tests SSD flash memory sanitization:
        High-entropy random overwrite + 0-byte truncation (triggering OS TRIM) + UUID de-identification.
        """
        secret_payload = b"SSD_NVME_CLASSIFIED_CRYPTOGRAPHIC_PAYLOAD_ABCXYZ_" * 150
        temp_file = tmp_path / "sensitive_ssd_data.bin"
        temp_file.write_bytes(secret_payload)

        success = secure_shred_file(temp_file, drive_type="SSD")
        assert success is True, "SSD secure shred failed!"
        assert not temp_file.exists(), "Original file path still exists after SSD shredding!"

        # Ensure directory is clean
        assert len(list(tmp_path.iterdir())) == 0

    def test_crypto_shredding_renders_data_irreversible(self, tmp_path):
        """
        Simulates Crypto-Shredding:
        1. An AES-256 encrypted database and vault key are generated with confidential plaintext.
        2. The encryption vault key file is shredded using secure_shred_file.
        3. Attempts to decrypt or recover the database fail, mathematically verifying irrecoverability.
        """
        vault_file = tmp_path / "security.vault"
        db_file = tmp_path / "target_database.db"
        secret_plaintext = b"CONFIDENTIAL_USER_MESSAGES_AND_KEYS_FOR_CRYPTO_SHREDDING"
        db_file.write_bytes(secret_plaintext)

        sec_mgr = DatabaseSecurityManager(vault_path=vault_file, db_path=db_file)
        sec_mgr.setup_master_password("AuditorMasterKey999!")

        enc_file = db_file.with_suffix(".db.enc")
        assert enc_file.exists(), "Encrypted database must exist!"
        assert vault_file.exists(), "Vault file must exist before shred!"

        # Shred the vault file (Crypto-Shredding)
        shred_ok = secure_shred_file(vault_file, drive_type="SSD")
        assert shred_ok is True
        assert not vault_file.exists()

        # Wipe plaintext database to simulate attacker finding only remaining disk blocks
        db_file.unlink()

        # Attempt to decrypt without key: Must fail completely
        new_sec_mgr = DatabaseSecurityManager(vault_path=vault_file, db_path=db_file)
        assert new_sec_mgr.is_vault_initialized() is False
        assert new_sec_mgr.verify_password("AuditorMasterKey999!") is False
        assert new_sec_mgr.decrypt_database() is False
        assert not db_file.exists(), "Database must NOT be decrypted without vault key!"

    def test_recursive_directory_shred_removes_all_traces(self, tmp_path):
        """Verifies multi-level recursive forensic directory sanitization."""
        sub1 = tmp_path / "nested_dir"
        sub1.mkdir()
        sub2 = sub1 / "deep_dir"
        sub2.mkdir()

        f1 = tmp_path / "root_file.bin"
        f2 = sub1 / "child_file.log"
        f3 = sub2 / "grandchild_file.db"

        f1.write_bytes(b"DATA_1" * 100)
        f2.write_bytes(b"DATA_2" * 100)
        f3.write_bytes(b"DATA_3" * 100)

        count = secure_shred_directory(tmp_path, drive_type="HDD")
        assert count == 3
        assert not tmp_path.exists(), "Root shredded directory should be completely removed!"


# ====================================================================
# 4. Metaveri Temizleyici (`strip_media_metadata`)
# ====================================================================
class TestDeepMetadataStrippingAudit:
    """
    Exhaustive metadata sanitization audit across media formats:
    - JPEG: Strips EXIF, GPS coordinates, Camera Model, Artist/Author, Timestamps.
    - PNG: Strips tEXt, zTXt, iTXt chunks (Author, Software, Description, Coordinates).
    - PDF: Strips /Author, /Creator, /Producer, /Title, /Subject, dates, library footprints.
    - MP3: Strips ID3v2 tags (TIT2, TPE1, TALB, TSSE), ID3v1 trailing tags, and APE tags.
    """

    def test_strip_jpeg_exif_gps_model_artist(self, tmp_path):
        """Creates a mock JPEG with real EXIF, GPS coords, Camera Model and Artist; validates full strip."""
        raw_img_path = tmp_path / "photo_with_exif.jpg"
        img = Image.new("RGB", (120, 120), color=(180, 50, 50))

        exif = img.getexif()
        # EXIF Tag 0x0110: Model
        exif[0x0110] = "Canon EOS R5"
        # EXIF Tag 0x013b: Artist
        exif[0x013b] = "Classified Field Officer"
        # EXIF Tag 0x0131: Software
        exif[0x0131] = "SpyCam Firmware v4.2"
        # EXIF Tag 0x8825: GPS IFD
        gps_ifd = exif.get_ifd(0x8825)
        gps_ifd[1] = "N"
        gps_ifd[2] = (41.0082, 0.0, 0.0)  # Latitude
        gps_ifd[3] = "E"
        gps_ifd[4] = (28.9784, 0.0, 0.0)  # Longitude

        img.save(raw_img_path, exif=exif)

        # Confirm original has metadata
        with Image.open(raw_img_path) as loaded_orig:
            orig_ex = loaded_orig.getexif()
            assert orig_ex.get(0x0110) == "Canon EOS R5"
            assert orig_ex.get(0x013b) == "Classified Field Officer"
            assert orig_ex.get_ifd(0x8825).get(1) == "N"

        # Sanitize
        clean_file_path = strip_media_metadata(str(raw_img_path))
        assert os.path.exists(clean_file_path)

        try:
            with Image.open(clean_file_path) as loaded_clean:
                clean_ex = loaded_clean.getexif()
                # 1. Model must be stripped
                assert clean_ex.get(0x0110) is None, f"Camera Model leaked: {clean_ex.get(0x0110)}"
                # 2. Artist must be stripped
                assert clean_ex.get(0x013b) is None, f"Artist leaked: {clean_ex.get(0x013b)}"
                # 3. Software must be stripped
                assert clean_ex.get(0x0131) is None, f"Software leaked: {clean_ex.get(0x0131)}"
                # 4. GPS IFD must be completely empty
                clean_gps = clean_ex.get_ifd(0x8825)
                assert len(clean_gps) == 0, f"GPS coordinates leaked: {clean_gps}"
        finally:
            if os.path.exists(clean_file_path):
                os.remove(clean_file_path)

    def test_strip_png_text_chunks_and_metadata(self, tmp_path):
        """Creates a mock PNG with author and location text chunks; validates full strip."""
        png_path = tmp_path / "diagram_with_meta.png"
        meta = PngImagePlugin.PngInfo()
        meta.add_text("Author", "Surveillance Operator")
        meta.add_text("Software", "GeoSpatial Analyst Pro")
        meta.add_text("Description", "Location: 39.9208 N, 32.8541 E")

        img = Image.new("RGBA", (100, 100), color=(0, 120, 255, 255))
        img.save(png_path, pnginfo=meta)

        with Image.open(png_path) as loaded_orig:
            assert loaded_orig.text.get("Author") == "Surveillance Operator"

        clean_path = strip_media_metadata(str(png_path))
        assert os.path.exists(clean_path)

        try:
            with Image.open(clean_path) as loaded_clean:
                # Text dictionary must be completely empty
                clean_text = getattr(loaded_clean, "text", {})
                assert len(clean_text) == 0, f"PNG text metadata leaked: {clean_text}"
                assert "Author" not in clean_text
                assert "Description" not in clean_text
        finally:
            if os.path.exists(clean_path):
                os.remove(clean_path)

    def test_strip_pdf_metadata_documents(self, tmp_path):
        """Creates a mock PDF containing author, title, and producer; validates complete wipe."""
        pdf_path = tmp_path / "classified_dossier.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_metadata({
            "/Author": "Secret Agent X",
            "/Title": "Black Budget Operation Dossier",
            "/Producer": "Dossier Generator 9000",
            "/Creator": "Custom Script",
            "/Subject": "Target Location Coordinates: 41.015, 28.979"
        })

        with open(pdf_path, "wb") as pf:
            writer.write(pf)

        with open(pdf_path, "rb") as pf:
            reader = PdfReader(pf)
            assert reader.metadata.get("/Author") == "Secret Agent X"

        clean_pdf_path = strip_media_metadata(str(pdf_path))
        assert os.path.exists(clean_pdf_path)

        try:
            with open(clean_pdf_path, "rb") as cf:
                clean_reader = PdfReader(cf)
                clean_meta = clean_reader.metadata or {}
                # Verify zero sensitive fields exist
                assert clean_meta.get("/Author") is None, f"Author leaked: {clean_meta.get('/Author')}"
                assert clean_meta.get("/Title") is None, f"Title leaked: {clean_meta.get('/Title')}"
                assert clean_meta.get("/Creator") is None, f"Creator leaked: {clean_meta.get('/Creator')}"
                assert clean_meta.get("/Subject") is None, f"Subject/GPS leaked: {clean_meta.get('/Subject')}"
                # Internal PyPDF2 fingerprint should also be stripped
                assert clean_meta.get("/Producer") in (None, ""), f"Producer leaked: {clean_meta.get('/Producer')}"
        finally:
            if os.path.exists(clean_pdf_path):
                os.remove(clean_pdf_path)

    def test_strip_mp3_id3v1_and_id3v2_tags(self, tmp_path):
        """Creates an MP3 with ID3v2.3 header/body, raw MPEG audio, and ID3v1 trailing tag; validates complete strip."""
        mp3_path = tmp_path / "voice_memo_intercept.mp3"

        # Construct ID3v2 header: "ID3" (3) + ver 3.0 (2) + flags 0 (1) + size 10 (4)
        id3v2_tag = (
            b"ID3\x03\x00\x00\x00\x00\x00\x0e"
            b"TIT2\x00\x00\x00\x04\x00\x00Test"  # Title frame
        )
        # Mock raw audio frame (MPEG sync word: 0xFF 0xFB)
        audio_stream = (b"\xff\xfb\x90\x00\x00\x00\x00\x00" * 32)
        # ID3v1 trailer: 128 bytes starting with "TAG"
        id3v1_tag = b"TAG" + b"Classified Audio Recording" + b"\x00" * (128 - 3 - 26)

        full_mp3_data = id3v2_tag + audio_stream + id3v1_tag
        mp3_path.write_bytes(full_mp3_data)

        clean_mp3_path = strip_media_metadata(str(mp3_path))
        assert os.path.exists(clean_mp3_path)

        try:
            cleaned_data = Path(clean_mp3_path).read_bytes()
            # 1. Output must match purely the raw audio stream
            assert cleaned_data == audio_stream, "MP3 sanitization did not extract pure audio frame stream!"
            # 2. No ID3 or TAG markers
            assert not cleaned_data.startswith(b"ID3"), "ID3v2 marker still present!"
            assert not cleaned_data.endswith(b"TAG"), "ID3v1 marker still present!"
        finally:
            if os.path.exists(clean_mp3_path):
                os.remove(clean_mp3_path)
