import os
import tempfile
from pathlib import Path
from shredder import secure_shred_file, secure_shred_directory, detect_drive_type


def test_detect_drive_type():
    drive = detect_drive_type()
    assert drive in ("SSD", "HDD")


def test_secure_shred_hdd_mode():
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(b"MAGNETIC_HDD_CONFIDENTIAL_DATA_1234567890")
        tf_path = Path(tf.name)

    assert tf_path.exists()
    assert tf_path.stat().st_size > 0

    success = secure_shred_file(tf_path, drive_type="HDD")
    assert success is True
    assert not tf_path.exists()


def test_secure_shred_ssd_mode():
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(b"SOLID_STATE_NVME_CONFIDENTIAL_DATA_1234567890")
        tf_path = Path(tf.name)

    assert tf_path.exists()
    assert tf_path.stat().st_size > 0

    success = secure_shred_file(tf_path, drive_type="SSD")
    assert success is True
    assert not tf_path.exists()


def test_secure_shred_directory_isolated():
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_shred_dir_"))
    sub_file_1 = tmp_dir / "secret1.txt"
    sub_file_2 = tmp_dir / "secret2.bin"
    sub_dir = tmp_dir / "sub"
    sub_dir.mkdir()
    sub_file_3 = sub_dir / "secret3.db"

    sub_file_1.write_bytes(b"DATA1")
    sub_file_2.write_bytes(b"DATA2" * 100)
    sub_file_3.write_bytes(b"DATA3" * 50)

    count = secure_shred_directory(tmp_dir, drive_type="SSD")
    assert count >= 3
    assert not tmp_dir.exists()
