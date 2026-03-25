"""
test_swap.py – E2E tests for the BSW image swap path (command '3').

The swap rotates:   SWAP ← BOOT;  BOOT ← UPDATE;  UPDATE ← SWAP

After a successful swap:
  - The BOOT slot contains what was previously in UPDATE.
  - The SWAP slot contains what was previously in BOOT.
  - The rollback counter is updated to the new BOOT version if it is higher.
  - The COMM status word is written to COMM_STATUS_SWAP (123) to coordinate
    the two-phase swap (BSW writes it before resetting for OB change, then
    checks it on the next boot).
"""

import struct
import pytest

from conftest import reset_and_connect
from helpers import board, serial_comm
from helpers.image_factory import ImageFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slot_version(address: int) -> int:
    raw = board.flash_read(address, 8)
    _crc, _magic, version = struct.unpack("<IHH", raw)
    return version


# ---------------------------------------------------------------------------
# TestSwapHappyPath
# ---------------------------------------------------------------------------

class TestSwapHappyPath:
    """Happy-path swap: BOOT=v1, UPDATE=v2, COMM=SWAP-ready, WRP unlocked for swap."""

    @pytest.fixture(autouse=True)
    def setup_swap_state(self, clean_flash, image_factory: ImageFactory):
        """Set up BOOT=v1, UPDATE=v2 and prepare the OB/COMM for a swap."""
        boot_img   = image_factory.build(version=1)
        update_img = image_factory.build(version=2)
        board.flash_image(board.BOOT_FLASH_ADDRESS,   boot_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, update_img)
        board.set_rollback_counter(1)

        # Replicate setupSystemForImageSwap(): COMM=123, unlock BOOT+COUNTER
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER,
        )
        import time; time.sleep(1.5)

    def test_swap_performs_correctly(self, bsw, config):
        """ACK received; BOOT←UPDATE (v2), SWAP←old BOOT (v1), counter=2, sectors re-protected."""
        import time
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        ack = bsw.wait_for_ack(expected_sequence=0)
        assert ack is not None
        bsw.drain_debug_log(timeout=5.0)  # let the swap finish
        time.sleep(1.5)  # allow OB_Launch reset to complete

        assert _slot_version(board.BOOT_FLASH_ADDRESS) == 2,  "BOOT slot must hold UPDATE version after swap"
        assert _slot_version(board.SWAP_FLASH_ADDRESS) == 1,  "SWAP slot must hold old BOOT version after swap"
        assert board.get_rollback_counter() == 2,             "Rollback counter must be updated to new BOOT version"
        assert board.is_write_protected(board.OB_WRP_BOOT),   "BOOT sector must be re-protected after swap"
        assert board.is_write_protected(board.OB_WRP_COUNTER), "COUNTER sector must be re-protected after swap"

# ---------------------------------------------------------------------------
# TestSwapWrongOBState
# ---------------------------------------------------------------------------

class TestSwapWrongOBState:
    """BSW must refuse swap when COMM=123 but WRP is not in the expected unlocked state.

    checkSystemForImageSwap() requires BOTH BOOT and COUNTER to be unprotected.
    Any remaining protection must cause a NACK 12.
    """

    def test_nack_when_boot_still_protected(self, clean_flash, image_factory, bsw, config):
        """COMM=SWAP but BOOT sector is still write-protected → NACK 12."""
        boot_img   = image_factory.build(version=1)
        update_img = image_factory.build(version=2)
        board.flash_image(board.BOOT_FLASH_ADDRESS,   boot_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, update_img)
        board.set_rollback_counter(1)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        # Unprotect only COUNTER, leave BOOT protected
        board.set_write_protection(
            protect_mask=board.OB_WRP_BOOT,
            unprotect_mask=board.OB_WRP_COUNTER,
        )
        import time; time.sleep(1.5)

        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        assert exc_info.value.error_code == 12

        # Restore
        board.set_write_protection(protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER)
        time.sleep(1.5)

    def test_nack_when_counter_still_protected(self, clean_flash, image_factory, bsw, config):
        """COMM=SWAP but COUNTER sector is still write-protected → NACK 12."""
        boot_img   = image_factory.build(version=1)
        update_img = image_factory.build(version=2)
        board.flash_image(board.BOOT_FLASH_ADDRESS,   boot_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, update_img)
        board.set_rollback_counter(1)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        # Unprotect only BOOT, leave COUNTER protected
        board.set_write_protection(
            protect_mask=board.OB_WRP_COUNTER,
            unprotect_mask=board.OB_WRP_BOOT,
        )
        import time; time.sleep(1.5)

        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        assert exc_info.value.error_code == 12

        board.set_write_protection(protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER)
        time.sleep(1.5)

    def test_nack_when_both_still_protected(self, nominal_state, bsw, config):
        """COMM=SWAP but both sectors still protected (nominal WRP state) → NACK 12."""
        board.set_comm_status(board.COMM_STATUS_SWAP)

        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        assert exc_info.value.error_code == 12


# ---------------------------------------------------------------------------
# TestSwapGarbageComm
# ---------------------------------------------------------------------------

class TestSwapGarbageComm:
    """BSW must refuse swap when the COMM word is garbage or erased (0xFFFFFFFF)."""

    def test_nack_on_garbage_comm(self, clean_flash, image_factory, bsw, config):
        """COMM = 0xCAFEBABE (neither 321 nor 123) → NACK 12."""
        boot_img   = image_factory.build(version=1)
        update_img = image_factory.build(version=2)
        board.flash_image(board.BOOT_FLASH_ADDRESS,   boot_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, update_img)
        board.set_rollback_counter(1)
        board.set_comm_status(0xCAFEBABE)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER,
        )
        import time; time.sleep(1.5)

        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        assert exc_info.value.error_code == 12

        board.set_write_protection(protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER)
        time.sleep(1.5)

    def test_nack_on_erased_comm(self, clean_flash, image_factory, bsw, config):
        """COMM = 0xFFFFFFFF (erased flash) → NACK 12."""
        boot_img   = image_factory.build(version=1)
        update_img = image_factory.build(version=2)
        board.flash_image(board.BOOT_FLASH_ADDRESS,   boot_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, update_img)
        board.set_rollback_counter(1)
        # Leave COMM sector erased (0xFFFFFFFF) — do NOT write a status word
        board.flash_erase_slot(board.COMM_FLASH_ADDRESS)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER,
        )
        import time; time.sleep(1.5)

        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        assert exc_info.value.error_code == 12

        board.set_write_protection(protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER)
        time.sleep(1.5)


# ---------------------------------------------------------------------------
# TestSwapBadUpdateSlot
# ---------------------------------------------------------------------------

class TestSwapBadUpdateSlot:
    """BSW must reject swap when the UPDATE slot is empty, corrupt, or has a bad signature.

    checkUpdateVersion() calls imageLoad(UPDATE) which runs CRC + signature
    checks before reading the version field.
    """

    def test_nack_when_update_slot_empty(self, swap_ready_state, bsw, config):
        """UPDATE slot erased → imageGetHeader fails → NACK (via checkUpdateVersion)."""
        board.flash_erase_slot(board.UPDATE_FLASH_ADDRESS)

        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=10.0)

    def test_nack_when_update_has_bad_magic(self, swap_ready_state, bsw, config, image_factory):
        """UPDATE slot has wrong magic → imageGetHeader returns NULL → NACK."""
        good_img = image_factory.build(version=2)
        bad_img  = ImageFactory.corrupt_magic(good_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, bad_img)

        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=10.0)

    def test_nack_when_update_has_corrupt_crc(self, swap_ready_state, bsw, config, image_factory):
        """UPDATE slot has corrupted CRC → imageValidate fails → NACK."""
        good_img = image_factory.build(version=2)
        bad_img  = ImageFactory.corrupt_crc(good_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, bad_img)

        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=10.0)

    def test_nack_when_update_has_invalid_signature(self, swap_ready_state, bsw, config, image_factory):
        """UPDATE slot CRC is valid but signature is tampered → imageLoad fails → NACK."""
        good_img  = image_factory.build(version=2)
        bad_sig   = ImageFactory.corrupt_signature(good_img)
        import binascii
        new_crc   = binascii.crc32(bad_sig[4:]) & 0xFFFFFFFF
        bad_img   = struct.pack("<I", new_crc) + bad_sig[4:]
        board.flash_image(board.UPDATE_FLASH_ADDRESS, bad_img)

        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=15.0)

    def test_debug_log_when_update_empty(self, swap_ready_state, bsw, config):
        """Debug log must mention a header or image validation failure."""
        board.flash_erase_slot(board.UPDATE_FLASH_ADDRESS)

        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=10.0)
        except serial_comm.NackReceived:
            pass
        log = "".join(bsw.drain_debug_log(timeout=3.0))
        assert "No valid header" in log or "failed" in log.lower() or "invalid" in log.lower()


# ---------------------------------------------------------------------------
# TestSwapVersionRejectionRecovery
# ---------------------------------------------------------------------------

class TestSwapVersionRejectionRecovery:
    """After checkUpdateVersion() rejects with NACK 9, the BSW must restore nominal state.

    setupSystemForNominal() is called: COMM ← 321, BOOT and COUNTER re-protected.
    """

    @pytest.fixture(autouse=True)
    def setup_rollback_scenario(self, clean_flash, image_factory):
        """Counter = 5, BOOT = v5, UPDATE = v3 (below floor=4).  System in SWAP state."""
        boot_img   = image_factory.build(version=5)
        update_img = image_factory.build(version=3)  # below floor
        board.flash_image(board.BOOT_FLASH_ADDRESS,   boot_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, update_img)
        board.set_rollback_counter(5)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER,
        )
        import time; time.sleep(1.5)

    def test_nack_9_on_version_below_floor(self, bsw, config):
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=10.0)
        assert exc_info.value.error_code == 9

    def test_comm_reset_to_nominal_after_rejection(self, bsw, config):
        """COMM word must revert to NOMINAL (321) after the rollback rejection."""
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=10.0)
        except serial_comm.NackReceived:
            pass
        import time; time.sleep(2.5)  # allow OB_Launch reset
        assert board.get_comm_status() == board.COMM_STATUS_NOMINAL

    def test_sectors_reprotected_after_rejection(self, bsw, config):
        """BOOT and COUNTER must be re-protected after the rollback rejection."""
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=10.0)
        except serial_comm.NackReceived:
            pass
        import time; time.sleep(2.5)
        assert board.is_write_protected(board.OB_WRP_BOOT),    "BOOT sector must be re-protected"
        assert board.is_write_protected(board.OB_WRP_COUNTER), "COUNTER sector must be re-protected"


# ---------------------------------------------------------------------------
# TestSwapRollbackCounterEdges
# ---------------------------------------------------------------------------

class TestSwapRollbackCounterEdges:
    """Rollback counter update edge cases in updateRollbackCounter()."""

    def test_counter_not_incremented_when_already_current(self, swap_ready_state, bsw, config):
        """If the counter already equals the new BOOT version, it must stay unchanged."""
        # swap_ready_state: BOOT=v1, UPDATE=v2, counter=1.
        # After swap: new BOOT=v2, counter should become 2.
        # Pre-set counter = 2 so the new BOOT version == counter.
        board.set_rollback_counter(2)

        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.drain_debug_log(timeout=5.0)
        import time; time.sleep(2.0)

        # Counter was already 2 (== new BOOT version 2); must stay 2.
        assert board.get_rollback_counter() == 2

    def test_counter_updated_when_new_boot_is_higher(self, swap_ready_state, bsw, config):
        """Counter must advance to the new BOOT version when it is higher."""
        # swap_ready_state already has counter=1, BOOT=v1, UPDATE=v2.
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.drain_debug_log(timeout=5.0)
        import time; time.sleep(2.0)

        assert board.get_rollback_counter() == 2
