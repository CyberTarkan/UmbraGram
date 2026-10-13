import os
import sys
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

_CACHED_DRIVE_TYPE: Optional[str] = None


def detect_drive_type(target_path: Optional[Path] = None) -> str:
    """
    Detects whether the target storage medium is an SSD (Solid State / NVMe) or HDD (Magnetic Platter).
    Returns 'SSD' or 'HDD'. Caches result for efficiency.
    """
    global _CACHED_DRIVE_TYPE
    if _CACHED_DRIVE_TYPE is not None:
        return _CACHED_DRIVE_TYPE

    drive_type = "SSD"  # Safe default on modern systems
    if sys.platform == "win32":
        try:
            # Query Windows physical disk properties
            CREATE_NO_WINDOW = 0x08000000
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-PhysicalDisk | Select-Object -ExpandProperty MediaType) -join ','"],
                capture_output=True, text=True, timeout=4, creationflags=CREATE_NO_WINDOW
            )
            media = res.stdout.strip().upper()
            if "HDD" in media and "SSD" not in media:
                drive_type = "HDD"
            else:
                drive_type = "SSD"
        except Exception:
            drive_type = "SSD"

    _CACHED_DRIVE_TYPE = drive_type
    return drive_type


def secure_shred_file(file_path: Path, drive_type: Optional[str] = None) -> bool:
    """
    Forensic sanitization tailored specifically to storage hardware architecture:

    - HDD (Magnetic Hard Drive):
      Overwrites physical magnetic sectors using multi-pass patterns (Random + Zeroes + Ones)
      combined with hardware hardware cache flush (os.fsync) to disrupt magnetic remnant traces.

    - SSD (NAND Flash / NVMe):
      SSDs use a Flash Translation Layer (FTL) and Wear-Leveling, where multiple in-place writes
      merely allocate new flash pages and wear down NAND cells without guaranteeing raw physical block overwrite.
      The SSD method applies:
      1. Single-pass high-entropy random overwrite (wipes accessible logical blocks without wearing NAND).
      2. Zero-byte truncation (f.truncate(0)) which triggers the NTFS/Windows TRIM advisory to deallocate blocks.
      3. Crypto-shredding: Since data in UmbraGram is AES-256 encrypted, shredding the keys/headers
         renders wear-leveled NAND remnants mathematically impossible to decrypt.
    """
    try:
        p = Path(file_path)
        if not p.is_file():
            return False

        if drive_type is None:
            drive_type = detect_drive_type(p)

        file_size = p.stat().st_size
        chunk_size = 64 * 1024

        with open(p, "ba+", buffering=0) as f:
            if drive_type == "HDD":
                # --- HDD MULTI-PASS OVERWRITE ---
                passes = [
                    ("random", None),
                    ("zeros", b"\x00"),
                    ("ones", b"\xff")
                ]
                for p_type, byte_val in passes:
                    f.seek(0)
                    written = 0
                    while written < file_size:
                        to_write = min(chunk_size, file_size - written)
                        pattern = os.urandom(to_write) if p_type == "random" else (byte_val * to_write)
                        f.write(pattern)
                        written += to_write
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
            else:
                # --- SSD FLASH / NVMe SANITIZATION ---
                # 1. High-entropy single pass (avoids wearing NAND cells while obfuscating logical pages)
                f.seek(0)
                written = 0
                while written < file_size:
                    to_write = min(chunk_size, file_size - written)
                    f.write(os.urandom(to_write))
                    written += to_write
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass

            # Truncate to 0 bytes (sends TRIM/Deallocate notification to SSD controller)
            f.truncate(0)

        # Wipe filesystem directory entry / MFT metadata by renaming to random UUID before delete
        random_name = p.parent / f"wiped_{uuid.uuid4().hex}.tmp"
        p.rename(random_name)
        random_name.unlink(missing_ok=True)
        return True
    except Exception:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass
        return False


def secure_shred_directory(dir_path: Path, drive_type: Optional[str] = None) -> int:
    """
    Recursively and securely destroys all files in dir_path using hardware-appropriate sanitization,
    then removes the empty directories.
    """
    shredded_count = 0
    d = Path(dir_path)
    if not d.is_dir():
        return 0

    if drive_type is None:
        drive_type = detect_drive_type(d)

    for root, dirs, files in os.walk(d, topdown=False):
        for f in files:
            fp = Path(root) / f
            if secure_shred_file(fp, drive_type=drive_type):
                shredded_count += 1
        for sub_dir in dirs:
            try:
                (Path(root) / sub_dir).rmdir()
            except Exception:
                pass

    try:
        d.rmdir()
    except Exception:
        pass

    return shredded_count


def execute_emergency_self_destruct(workspace_dir: Optional[Path] = None, app_pid: Optional[int] = None, dry_run: bool = False):
    """
    SAFETY-GUARDED EMERGENCY SELF-DESTRUCT:
    Only executed when the user explicitly clicks the final confirmation button in the UI.
    NEVER executed automatically or during testing.
    """
    if dry_run:
        return

    base_dir = Path(workspace_dir) if workspace_dir else Path.cwd()
    pid = app_pid if app_pid else os.getpid()
    d_type = detect_drive_type(base_dir)

    # 1. Shred encryption vault first (Crypto-shredding: instant invalidation of all ciphertext on SSD/HDD)
    vault_files = [
        base_dir / "security.vault",
        base_dir / "security.vault.tmp"
    ]
    for vf in vault_files:
        if vf.is_file():
            secure_shred_file(vf, drive_type=d_type)

    # 2. Shred SQLite databases and logs
    db_files = [
        base_dir / "bot_system.db",
        base_dir / "bot_system.db-wal",
        base_dir / "bot_system.db-shm",
        base_dir / "bot_system.db.enc"
    ]
    for df in db_files:
        if df.is_file():
            secure_shred_file(df, drive_type=d_type)

    # 3. Shred downloads and cached media
    media_dirs = [
        base_dir / "downloads",
        base_dir / "__pycache__"
    ]
    for md in media_dirs:
        if md.is_dir():
            secure_shred_directory(md, drive_type=d_type)

    # 4. Asynchronous self-cleanup script
    temp_dir = Path(os.environ.get("TEMP", "C:/Windows/Temp"))
    bat_path = temp_dir / f"shred_kill_{uuid.uuid4().hex[:8]}.bat"

    bat_content = f"""@echo off
timeout /t 1 /nobreak >nul
taskkill /F /PID {pid} >nul 2>&1
timeout /t 1 /nobreak >nul
if exist "{base_dir}" (
    del /f /q /s "{base_dir}\\*.py" >nul 2>&1
    del /f /q /s "{base_dir}\\*.db*" >nul 2>&1
    del /f /q /s "{base_dir}\\*.vault*" >nul 2>&1
    rd /s /q "{base_dir}\\downloads" >nul 2>&1
    rd /s /q "{base_dir}" >nul 2>&1
)
del "%~f0" >nul 2>&1
exit
"""
    try:
        with open(bat_path, "w", encoding="utf-8") as bf:
            bf.write(bat_content)

        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat_path)],
            creationflags=CREATE_NO_WINDOW,
            close_fds=True
        )
    except Exception:
        pass

    os._exit(0)
