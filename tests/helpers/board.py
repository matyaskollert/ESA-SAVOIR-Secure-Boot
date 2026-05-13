"""
board.py - Low-level board operations for E2E tests.

Uses STM32CubeProgrammer CLI (STM32_Programmer_CLI.exe) for all board
interactions. Runs natively on Windows.

Flash memory map (STM32F439ZI):
    0x08000000  Sectors 0-4  BSW (bootloader) - never overwritten by tests
    0x08020000  Sector 5     SLOT_A image slot  (128 KB)
    0x08040000  Sector 6     SLOT_B image slot  (128 KB)
    0x08060000  Sector 7     SWAP   (image copy scratch space for hardware swap, 128 KB)
    0x08080000  Sector 8     COMM   (bootloader status word, 4 B)
    0x080A0000  Sector 9     PROTECTED_BSW_STATE (rollback_counter + primary_slot)
    0x080C0000  Sector 10    REPORT

Option-byte notes (STM32F4 nWRP field, 12 bits):
    Bit N of nWRP corresponds to sector N.
    0 = sector write-protected,  1 = sector write-unprotected.
    Nominal state: OB_WRP_SLOT_A and OB_WRP_PROTECTED_BSW_STATE bits are both 0 (protected).

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
SLOT_A_FLASH_ADDRESS = 0x08020000  # first image partition (sector 5)
SLOT_B_FLASH_ADDRESS = 0x08040000  # second image partition (sector 6)
COMM_FLASH_ADDRESS = 0x08080000
PROTECTED_BSW_STATE_FLASH_ADDRESS = (
    0x080A0000  # holds protected_bsw_state_t (rollback_counter + primary_slot)
)
FLASH_SECTOR_SIZE = 128 * 1024  # 128 KB (sectors 5-11)

# protected_bsw_state_t field offsets (matching the C struct layout)
PROTECTED_BSW_STATE_COUNTER_OFFSET = 0  # uint32_t rollback_counter
PROTECTED_BSW_STATE_PRIMARY_SLOT_OFFSET = 4  # uint32_t primary_slot
PROTECTED_BSW_STATE_PRIMARY_SLOT_A = 0xAAAAAAAA
PROTECTED_BSW_STATE_PRIMARY_SLOT_B = 0xBBBBBBBB

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
OB_WRP_SLOT_A = 1 << 5  # SLOT_A sector 5
OB_WRP_SLOT_B = 1 << 6  # SLOT_B sector 6
OB_WRP_PROTECTED_BSW_STATE = 1 << 9  # protected BSW state sector 9

# Full nWRP bitmask for every sector managed by the tests.
# Used by _temporarily_unprotected() to detect and lift WRP before writes.
_ADDR_TO_OB_MASK = {
    0x08020000: OB_WRP_SLOT_A,  # SLOT_A
    0x08040000: OB_WRP_SLOT_B,  # SLOT_B
    0x08060000: 1 << 7,  # SWAP
    0x08080000: 1 << 8,  # COMM
    0x080A0000: OB_WRP_PROTECTED_BSW_STATE,  # protected BSW state
    0x080C0000: 1 << 10,  # REPORT
    0x080E0000: 1 << 11,
}

# BSW status words
COMM_STATUS_NOMINAL = 0xAA
COMM_STATUS_STANDBY = 0xBB
COMM_STATUS_SWAP = 0xCC
COMM_STATUS_BOOT_ATTEMPTED = 0xDD

# ---------------------------------------------------------------------------
# BSW report flash constants (mirror bsw_report.h / flash.h)
# ---------------------------------------------------------------------------
REPORT_FLASH_ADDRESS = 0x080C0000  # sector 10
BSW_REPORT_MAGIC = 0xBEEF0042
BSW_REPORT_MAX_COUNT = 5
BSW_REPORT_SLOT_SIZE = 20  # sizeof(bsw_report_t), packed

# ImageSlot enum values (SLOT_A=0, SLOT_B=1, must match C enum)
IMAGE_SLOT_A = 0
IMAGE_SLOT_B = 1

# Report type codes
BSW_REPORT_TYPE_NOMINAL = 0x01
BSW_REPORT_TYPE_UPDATE = 0x02
BSW_REPORT_TYPE_SWAP = 0x03

# Step flags - NOMINAL boot
BSW_NOMINAL_FLAG_STATUS_SET = 1 << 0  # BOOT_ATTEMPTED status written
BSW_NOMINAL_FLAG_CRC_OK = 1 << 1  # Flash CRC passed
BSW_NOMINAL_FLAG_SIG_OK = 1 << 2  # Digital signature passed
BSW_NOMINAL_FLAG_RAM_CRC_OK = 1 << 3  # RAM copy CRC passed
BSW_NOMINAL_FLAG_SYSTEM_OK = 1 << 4  # checkSystemForNominal() passed

# Step flags - UPDATE
BSW_UPDATE_FLAG_VERSION_OK = 1 << 0  # Version >= rollback floor
BSW_UPDATE_FLAG_RAM_CRC_OK = 1 << 1  # Received image CRC passed
BSW_UPDATE_FLAG_RAM_SIG_OK = 1 << 2  # Received image signature valid
BSW_UPDATE_FLAG_FLASH_OK = 1 << 3  # Image written to secondary slot
BSW_UPDATE_FLAG_SYSTEM_OK = 1 << 4  # checkSystemForUpdate() passed

# Step flags - SWAP
BSW_SWAP_FLAG_VERSION_OK = 1 << 0  # Secondary version >= floor
BSW_SWAP_FLAG_CRC_OK = 1 << 1  # Secondary CRC passed
BSW_SWAP_FLAG_SIG_OK = 1 << 2  # Secondary signature verified
BSW_SWAP_FLAG_COUNTER_OK = 1 << 3  # Rollback counter written
BSW_SWAP_FLAG_SLOT_FLIPPED = 1 << 4  # Primary-slot flag updated
BSW_SWAP_FLAG_SYSTEM_OK = 1 << 5  # checkSystemForImageSwap() passed


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run(extra_args, check=True) -> tuple[str, str]:
    """Run STM32_Programmer_CLI with extra_args and return the result."""
    cmd = [STM32CUBEPROG] + _CONNECT + extra_args
    result = subprocess.run(cmd, capture_output=True)
    # STM32CubeProgrammer outputs non-UTF-8 bytes on Windows (e.g. Windows-1252
    # symbols in its banner).  Decode as cp1252 with a fallback replacement so
    # we never get a UnicodeDecodeError, and the output is always a str.
    stdout = result.stdout.decode("cp1252", errors="replace") if result.stdout else ""
    stderr = result.stderr.decode("cp1252", errors="replace") if result.stderr else ""
    if check and result.returncode != 0:
        raise RuntimeError(
            f"STM32CubeProgrammer failed (exit {result.returncode}):\n"
            f"Command: {' '.join(cmd)}\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )
    return stdout, stderr


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
# COMM / BSW state
# ---------------------------------------------------------------------------


def set_comm_status(status):
    """Write the BSW status word to the COMM flash sector."""
    flash_write_word(COMM_FLASH_ADDRESS, status)


def get_comm_status():
    """Read the BSW status word from the COMM flash sector."""
    raw = flash_read(COMM_FLASH_ADDRESS, 4)
    return struct.unpack("<I", raw)[0]


def set_rollback_counter(value):
    """Write the rollback counter field of protected_bsw_state_t.
    The primary_slot field is read back first and preserved.
    """
    primary_slot = get_primary_flag()
    import struct as _struct

    data = _struct.pack("<II", value, primary_slot)
    flash_write(PROTECTED_BSW_STATE_FLASH_ADDRESS, data)


def get_rollback_counter():
    """Read the rollback_counter field from the protected BSW state sector."""
    raw = flash_read(
        PROTECTED_BSW_STATE_FLASH_ADDRESS + PROTECTED_BSW_STATE_COUNTER_OFFSET, 4
    )
    return struct.unpack("<I", raw)[0]


def get_primary_flag():
    """Read the primary_slot field from the protected BSW state sector.
    Returns PROTECTED_BSW_STATE_PRIMARY_SLOT_B when SLOT_B is primary,
    or 0xFFFFFFFF (erased default) / PROTECTED_BSW_STATE_PRIMARY_SLOT_A otherwise.
    """
    raw = flash_read(
        PROTECTED_BSW_STATE_FLASH_ADDRESS + PROTECTED_BSW_STATE_PRIMARY_SLOT_OFFSET, 4
    )
    return struct.unpack("<I", raw)[0]


def set_primary_flag(flag):
    """Write the primary_slot field of protected_bsw_state_t while preserving the rollback counter."""
    counter = get_rollback_counter()
    import struct as _struct

    data = _struct.pack("<II", counter, flag)
    flash_write(PROTECTED_BSW_STATE_FLASH_ADDRESS, data)


def get_primary_slot():
    """Return the address of the currently-primary (active) image slot."""
    return (
        SLOT_B_FLASH_ADDRESS
        if get_primary_flag() == PROTECTED_BSW_STATE_PRIMARY_SLOT_B
        else SLOT_A_FLASH_ADDRESS
    )


def get_secondary_slot():
    """Return the address of the currently-secondary (inactive) image slot."""
    return (
        SLOT_A_FLASH_ADDRESS
        if get_primary_flag() == PROTECTED_BSW_STATE_PRIMARY_SLOT_B
        else SLOT_B_FLASH_ADDRESS
    )


def get_primary_slot_ob_mask():
    """Return the nWRP OB bitmask for the currently-primary image slot.

    Works for both swap modes:
      - Flag-based swap: the flag has already been updated to point to the new
        primary slot, so this returns that slot's mask.
      - Hardware swap: the flag still points to SLOT_A (which physically holds
        the new primary image after the data move), so this also returns the
        correct slot's mask.
    """
    return (
        OB_WRP_SLOT_B
        if get_primary_flag() == PROTECTED_BSW_STATE_PRIMARY_SLOT_B
        else OB_WRP_SLOT_A
    )


def get_secondary_slot_ob_mask():
    """Return the nWRP OB bitmask for the currently-secondary image slot."""
    return (
        OB_WRP_SLOT_A
        if get_primary_flag() == PROTECTED_BSW_STATE_PRIMARY_SLOT_B
        else OB_WRP_SLOT_B
    )


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
    output = result[0] + result[1]
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
            nwrp |= 1 << sector
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


# ---------------------------------------------------------------------------
# BSW report flash helpers
# ---------------------------------------------------------------------------


def erase_reports():
    """Erase the REPORT flash sector (sector 10, 0x080C0000), clearing all stored reports."""
    flash_erase_sector(REPORT_FLASH_ADDRESS)


def read_report(slot_index: int):
    """Read and parse one bsw_report_t slot from flash (0-based slot index).

    Returns a dict with parsed fields if the slot contains a valid report
    (magic == BSW_REPORT_MAGIC), or None if the slot is erased/invalid.

    Field layout matches the packed C struct in bsw_report.h:
      magic (4B), type (1B), outcome (1B), primary_slot (1B), pad (1B),
      rollback_counter (4B), primary_version (2B), secondary_version (2B),
      step_flags (4B)  →  total 20 bytes.
    """
    addr = REPORT_FLASH_ADDRESS + slot_index * BSW_REPORT_SLOT_SIZE
    data = flash_read(addr, BSW_REPORT_SLOT_SIZE)
    magic, rtype, outcome, primary_slot, _pad, counter, pver, sver, flags = (
        struct.unpack("<IBBBBIHHI", data)
    )
    if magic != BSW_REPORT_MAGIC:
        return None
    return {
        "magic": magic,
        "type": rtype,
        "outcome": outcome,
        "primary_slot": primary_slot,
        "rollback_counter": counter,
        "primary_version": pver,
        "secondary_version": sver,
        "step_flags": flags,
    }


def read_all_reports():
    """Read all BSW_REPORT_MAX_COUNT slots and return a list of valid report dicts.

    Reports are returned in slot order (slot 0 first).  Erased/invalid slots
    are omitted.  Use get_latest_report() if you only need the newest entry.
    """
    result = []
    for i in range(BSW_REPORT_MAX_COUNT):
        r = read_report(i)
        if r is not None:
            result.append(r)
    return result


def get_latest_report():
    """Return the most recently flushed report (age == 0) or None if no reports exist.

    Mirrors bsw_report_get_by_age(0): the newest report is one slot before
    g_next_idx (the first empty slot), wrapping around the circular buffer.
    """
    next_idx = BSW_REPORT_MAX_COUNT  # all slots filled → g_next_idx wraps to 0
    for i in range(BSW_REPORT_MAX_COUNT):
        if read_report(i) is None:
            next_idx = i
            break
    if next_idx == BSW_REPORT_MAX_COUNT:
        next_idx = 0
    newest_idx = (next_idx + BSW_REPORT_MAX_COUNT - 1) % BSW_REPORT_MAX_COUNT
    return read_report(newest_idx)
