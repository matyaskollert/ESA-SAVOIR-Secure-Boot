"""
board.py - Low-level board operations for E2E tests.

Uses STM32CubeProgrammer CLI (STM32_Programmer_CLI.exe) for all board
interactions. Runs natively on Windows.

Flash memory map (STM32F439ZI):
    0x08000000  Sectors 0-4  BSW (bootloader) - never overwritten by tests
    0x08020000  Sector 5     BOOT   image slot  (128 KB)
    0x08040000  Sector 6     UPDATE image slot  (128 KB)
    0x08060000  Sector 7     SWAP   image slot  (128 KB)
    0x08080000  Sector 8     COMM   (bootloader status word, 4 B)
    0x080A0000  Sector 9     COUNTER (rollback counter, 4 B)
    0x080C0000  Sector 10    REPORT

Option-byte notes (STM32F4 nWRP field, 12 bits):
    Bit N of nWRP corresponds to sector N.
    0 = sector write-protected,  1 = sector write-unprotected.
    Nominal state: OB_WRP_BOOT and OB_WRP_COUNTER bits are both 0 (protected).

    If STM32CubeProgrammer shows a different OB field name for your device
    revision, update the _NWRP_OB_NAME constant below.
"""

import os
import re
import struct
import subprocess
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration - override via environment variable.
# ---------------------------------------------------------------------------
STM32CUBEPROG = os.environ.get(
    "STM32CUBEPROG_BIN",
    r"C:\Program Files\STMicroelectronics\STM32Cube"
    r"\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe",
)

# SWD connection arguments prepended to every CLI call.
_CONNECT = ["-c", "port=SWD", "mode=NORMAL"]

# Flash addresses
BOOT_FLASH_ADDRESS    = 0x08020000
UPDATE_FLASH_ADDRESS  = 0x08040000
SWAP_FLASH_ADDRESS    = 0x08060000
COMM_FLASH_ADDRESS    = 0x08080000
COUNTER_FLASH_ADDRESS = 0x080A0000
FLASH_SECTOR_SIZE     = 128 * 1024  # 128 KB (sectors 5-11)

# Address to sector number used by the -e (erase) command.
_ADDR_TO_SECTOR = {
    0x08020000: 5,
    0x08040000: 6,
    0x08060000: 7,
    0x08080000: 8,
    0x080A0000: 9,
    0x080C0000: 10,
    0x080E0000: 11,
}

# nWRP bitmask constants (bit N = sector N; 0 = protected, 1 = unprotected)
OB_WRP_BOOT    = 1 << 5   # BOOT sector 5
OB_WRP_COUNTER = 1 << 9   # COUNTER sector 9

# Full nWRP bitmask for every sector managed by the tests.
# Used by _temporarily_unprotected() to detect and lift WRP before writes.
_ADDR_TO_OB_MASK = {
    0x08020000: 1 << 5,   # BOOT
    0x08040000: 1 << 6,   # UPDATE
    0x08060000: 1 << 7,   # SWAP
    0x08080000: 1 << 8,   # COMM
    0x080A0000: 1 << 9,   # COUNTER
    0x080C0000: 1 << 10,  # REPORT
    0x080E0000: 1 << 11,
}

# BSW status words
COMM_STATUS_NOMINAL        = 0xAA
COMM_STATUS_STANDBY        = 0xBB
COMM_STATUS_SWAP           = 0xCC
COMM_STATUS_BOOT_ATTEMPTED = 0xDD


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(extra_args, check=True):
    """Run STM32_Programmer_CLI with extra_args and return the result."""
    cmd = [STM32CUBEPROG] + _CONNECT + extra_args
    result = subprocess.run(cmd, capture_output=True)
    # STM32CubeProgrammer outputs non-UTF-8 bytes on Windows (e.g. Windows-1252
    # symbols in its banner).  Decode as cp1252 with a fallback replacement so
    # we never get a UnicodeDecodeError, and the output is always a str.
    result.stdout = result.stdout.decode("cp1252", errors="replace") if result.stdout else ""
    result.stderr = result.stderr.decode("cp1252", errors="replace") if result.stderr else ""
    if check and result.returncode != 0:
        raise RuntimeError(
            f"STM32CubeProgrammer failed (exit {result.returncode}):\n"
            f"Command: {' '.join(cmd)}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def _tmp_write(data):
    """Write data to a named temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".bin")
    os.write(fd, data)
    os.close(fd)
    return path


def _tmp_path(suffix=".bin"):
    """Create an empty named temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return path


import contextlib

@contextlib.contextmanager
def _temporarily_unprotected(address):
    """Context manager: if the sector at address is write-protected, lift the
    protection before the body runs and restore it afterwards.
    Sectors with no OB mask entry (e.g. BSW sectors 0-4) are left untouched.
    """
    ob_mask = _ADDR_TO_OB_MASK.get(address, 0)
    was_protected = ob_mask != 0 and is_write_protected(ob_mask)
    if was_protected:
        set_write_protection(protect_mask=0, unprotect_mask=ob_mask)
    try:
        yield
    finally:
        if was_protected:
            set_write_protection(protect_mask=ob_mask)


# ---------------------------------------------------------------------------
# Board reset
# ---------------------------------------------------------------------------

def reset_board(delay=0.5):
    """Reset the MCU via SWD."""
    _run(["-rst"])
    time.sleep(delay)


# ---------------------------------------------------------------------------
# Flash read / write / erase
# ---------------------------------------------------------------------------

def flash_read(address, size):
    """Read size bytes from device memory starting at address.
    Uses -u (upload) which produces a raw binary file.
    """
    path = _tmp_path()
    try:
        # STM32CubeProgrammer: -u <address> <size> <output_file>
        _run(["-u", hex(address), str(size), path])
        return Path(path).read_bytes()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def flash_write(address, data):
    """Write data to flash starting at address.
    If the target sector is write-protected the protection is lifted for the
    duration of the write and then restored automatically.
    """
    with _temporarily_unprotected(address):
        path = _tmp_write(data)
        try:
            _run(["-w", path, hex(address)])
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


def flash_write_word(address, value):
    """Write a single 32-bit little-endian word to address."""
    flash_write(address, struct.pack("<I", value))


def flash_erase_sector(address):
    """Erase the flash sector that contains address using the -e command.
    If the sector is write-protected the protection is lifted first and
    restored afterwards.
    """
    sector = _ADDR_TO_SECTOR.get(address)
    if sector is None:
        raise ValueError(
            f"No sector mapping for address {hex(address)}. "
            f"Known addresses: {[hex(a) for a in _ADDR_TO_SECTOR]}"
        )
    with _temporarily_unprotected(address):
        _run(["-e", str(sector)])


# ---------------------------------------------------------------------------
# Higher-level image-slot helpers
# ---------------------------------------------------------------------------

def flash_image(slot_address, image_data):
    """Write a complete signed+headered firmware image to slot_address."""
    flash_write(slot_address, image_data)


def flash_erase_slot(slot_address):
    """Erase an image slot so the BSW finds no valid header."""
    flash_erase_sector(slot_address)


def flash_corrupt_crc(slot_address):
    """Replace the CRC word at slot_address with 0xDEADBEEF.
    Reads the full sector, patches bytes [0:4], then rewrites it so
    the signature is unchanged and the signature test can reach sig verify.
    """
    data = flash_read(slot_address, FLASH_SECTOR_SIZE)
    corrupt = struct.pack("<I", 0xDEADBEEF) + data[4:]
    flash_write(slot_address, corrupt)


# ---------------------------------------------------------------------------
# COMM / COUNTER words
# ---------------------------------------------------------------------------

def set_comm_status(status):
    """Write the BSW status word to the COMM flash sector."""
    flash_write_word(COMM_FLASH_ADDRESS, status)


def get_comm_status():
    """Read the BSW status word from the COMM flash sector."""
    raw = flash_read(COMM_FLASH_ADDRESS, 4)
    return struct.unpack("<I", raw)[0]


def set_rollback_counter(value):
    """Write the rollback counter to the COUNTER flash sector."""
    flash_write_word(COUNTER_FLASH_ADDRESS, value)


def get_rollback_counter():
    """Read the rollback counter from the COUNTER flash sector."""
    raw = flash_read(COUNTER_FLASH_ADDRESS, 4)
    return struct.unpack("<I", raw)[0]


# ---------------------------------------------------------------------------
# Option bytes (nWRP write-protection) via STM32CubeProgrammer -ob
# ---------------------------------------------------------------------------

def _read_nwrp():
    """Read the current nWRP option-byte values via -ob displ.
    Returns a bitmask where bit N = 1 means sector N is NOT write-protected,
    bit N = 0 means sector N IS write-protected.
    Parses the individual nWRP0..nWRP23 fields shown by STM32CubeProgrammer.
    """
    result = _run(["-ob", "displ"])
    output = result.stdout + result.stderr
    # Each line looks like:  "     nWRP9        : 0x0 (Write protection active)"
    matches = re.findall(r"nWRP(\d+)\s*:\s*(0x[0-9a-fA-F]+)", output, re.IGNORECASE)
    if not matches:
        raise RuntimeError(
            "Could not parse nWRP0..nWRPx fields from -ob displ output.\n"
            f"Full output:\n{output}"
        )
    nwrp = 0
    for sector_str, val_str in matches:
        sector = int(sector_str)
        val = int(val_str, 16)
        if val != 0:  # 0x1 = unprotected
            nwrp |= (1 << sector)
    return nwrp


def is_write_protected(ob_bit_mask):
    """Return True if all sectors indicated by ob_bit_mask are write-protected.
    A sector is protected when its nWRP bit is 0.
    """
    nwrp = _read_nwrp()
    return (nwrp & ob_bit_mask) == 0


def set_write_protection(protect_mask, unprotect_mask=0):
    """Modify nWRP write-protection option bytes.

    protect_mask:   OR-ed OB_WRP_* bits to mark as protected   (set nWRPx=0x0)
    unprotect_mask: OR-ed OB_WRP_* bits to mark as unprotected (set nWRPx=0x1)

    STM32CubeProgrammer performs OB_Launch automatically, which resets the
    device.  A 1.5 s sleep is included to allow re-enumeration.
    """
    ob_args = []
    for bit in range(24):  # nWRP0..nWRP23
        mask = 1 << bit
        if protect_mask & mask:
            ob_args += ["-ob", f"nWRP{bit}=0x0"]
        elif unprotect_mask & mask:
            ob_args += ["-ob", f"nWRP{bit}=0x1"]
    if not ob_args:
        return
    # -y suppresses the confirmation prompt
    _run(["-y"] + ob_args)
    time.sleep(1.5)  # wait for OB_Launch reset to complete
