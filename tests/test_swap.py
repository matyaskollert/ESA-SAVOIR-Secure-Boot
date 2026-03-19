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

    def test_ack_received(self, bsw, config):
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        ack = bsw.wait_for_ack(expected_sequence=0)
        assert ack is not None

    def test_boot_slot_has_update_version_after_swap(self, bsw, config):
        """After swap, BOOT slot must have the version that was in UPDATE (v2)."""
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.drain_debug_log(timeout=3.0)  # let the swap finish

        assert _slot_version(board.BOOT_FLASH_ADDRESS) == 2

    def test_swap_slot_has_old_boot_version(self, bsw, config):
        """After swap, SWAP slot must hold the version that was previously in BOOT (v1)."""
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.drain_debug_log(timeout=3.0)

        assert _slot_version(board.SWAP_FLASH_ADDRESS) == 1

    def test_rollback_counter_updated(self, bsw, config):
        """Rollback counter must be updated to reflect the new BOOT version (2)."""
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.drain_debug_log(timeout=3.0)

        counter = board.get_rollback_counter()
        assert counter == 2

    def test_sectors_reprotected_after_swap(self, bsw, config):
        """After swap, BOOT and COUNTER sectors must be write-protected again."""
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.drain_debug_log(timeout=5.0)
        import time; time.sleep(1.5)  # OB_Launch may reset the board

        assert board.is_write_protected(board.OB_WRP_BOOT)
        assert board.is_write_protected(board.OB_WRP_COUNTER)


# ---------------------------------------------------------------------------
# TestSwapNotConfigured
# ---------------------------------------------------------------------------

class TestSwapNotConfigured:
    """BSW must refuse swap when COMM status is not SWAP (123)."""

    @pytest.fixture(autouse=True)
    def setup_wrong_comm(self, clean_flash, image_factory):
        """Set up valid images but leave COMM at nominal (321)."""
        boot_img   = image_factory.build(version=1)
        update_img = image_factory.build(version=2)
        board.flash_image(board.BOOT_FLASH_ADDRESS,   boot_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, update_img)
        board.set_comm_status(board.COMM_STATUS_NOMINAL)  # wrong for swap

    def test_nack_when_comm_not_swap(self, bsw, config):
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        assert exc_info.value.error_code == 12
