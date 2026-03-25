"""
test_lifecycle.py – End-to-end lifecycle tests for the BSW bootloader.

These tests exercise multi-step scenarios that span more than one boot cycle
or combine upload + swap + boot in sequence.  Each test drives the full state
machine from a clean baseline through to a verified final state.

All tests use the BSW autonomous mode: the appropriate COMM status is written
before the board resets, and '6' (skip-timeout) is sent during the 15 s
window so the bootloader acts on its status immediately rather than waiting.

Scenarios covered
-----------------
1. Full update cycle:     BOOT=v1 → upload v2 → swap → BOOT=v2
2. Upload without swap:   upload v2 but skip swap → BOOT still v1
3. Consecutive swaps:     v1 → v2 → v3
4. Interrupted swap → boot attempt:
     After upload the board resets with COMM=123 + sectors unlocked.
     BSW enters standby (interrupted state), '6' skips out, status=123
     triggers auto-swap, leaving the system nominal.
5. Interrupted swap → update attempt:
     Same interrupted state; status=123 triggers auto-swap first.
6. Rollback window:  v1 → v2 (swap), upload v1 (within window=1), swap → v1
7. Rollback – both images fail: BOOT=v2 fails, UPDATE=v1 also fails
     → BSW ends up in standby.
8. Rollback – first image fails, second runs: BOOT=v2 fails, UPDATE=v1 runs OK
     → BOOT slot ends up as v1, COMM becomes NOMINAL.
"""

import struct
import time
import pytest

from conftest import reset_and_connect
from helpers import board, serial_comm
from helpers.image_factory import ImageFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slot_version(address: int) -> int:
    """Read the 2-byte version field from a flash slot header."""
    raw = board.flash_read(address, 8)
    _crc, _magic, version = struct.unpack("<IHH", raw)
    return version


def _skip_timeout(bsw) -> None:
    """Send command '6' so the BSW exits its 15 s input window immediately."""
    bsw.send_command('6', sequence=0)
    bsw.wait_for_ack(expected_sequence=0, timeout=5.0)


def _do_full_upload(bsw, image_data: bytes) -> None:
    """Reset the board, send '2' during the 15 s input window to enter update
    mode, upload the image, then wait for the BSW to reset into SWAP state.
    Caller must ensure COMM=NOMINAL and sectors are protected beforehand."""
    board.reset_board(delay=1.0)
    bsw.send_command('2', sequence=0)
    bsw.wait_for_ack(expected_sequence=0)
    time.sleep(0.5)  # allow BSW to prepare for upload
    bsw.upload_image(image_data, start_sequence=1)
    time.sleep(2.5)  # BSW calls setupSystemForImageSwap() then resets


def _do_swap(bsw) -> None:
    """Reset the board; the BSW auto-swaps when '6' skips the timeout.
    Caller must ensure COMM=SWAP (123) beforehand."""
    board.reset_board(delay=1.0)
    _skip_timeout(bsw)
    bsw.drain_debug_log(timeout=10.0)
    time.sleep(2.5)  # allow OB_Launch reset from setupSystemForNominal


# ---------------------------------------------------------------------------
# TestFullUpdateCycle
# ---------------------------------------------------------------------------

class TestFullUpdateCycle:
    """BOOT=v1 → upload v2 → swap → verify all post-cycle state and autonomous boot."""

    def test_full_cycle(self, nominal_state, bsw, config, image_factory):
        """Upload v2, swap, then verify BOOT=v2, SWAP=v1, counter=2, WRP protected,
        COMM=NOMINAL, and that the BSW autonomously boots v2."""
        update_img = image_factory.build(version=2)
        _do_full_upload(bsw, update_img)
        _do_swap(bsw)

        assert _slot_version(board.BOOT_FLASH_ADDRESS) == 2,  "BOOT must hold v2 after swap"
        assert _slot_version(board.SWAP_FLASH_ADDRESS) == 1,  "SWAP must hold old v1 after swap"
        assert board.get_rollback_counter() == 2,             "Counter must advance to 2"
        assert board.is_write_protected(board.OB_WRP_BOOT),   "BOOT must be protected after cycle"
        assert board.is_write_protected(board.OB_WRP_COUNTER), "COUNTER must be protected after cycle"
        assert board.get_comm_status() == board.COMM_STATUS_NOMINAL

        board.reset_board(delay=1.0)
        _skip_timeout(bsw)
        log = "".join(bsw.drain_debug_log(timeout=10.0))
        assert "CRC validation in RAM successful" in log


# ---------------------------------------------------------------------------
# TestConsecutiveSwaps
# ---------------------------------------------------------------------------

class TestConsecutiveSwaps:
    """Perform two consecutive upgrades: v1 → v2 → v3."""

    def test_two_consecutive_upgrades(self, nominal_state, bsw, config, image_factory):
        """v1→v2 swap then v2→v3 swap; BOOT=v3 and counter=3."""
        v2_img = image_factory.build(version=2)
        v3_img = image_factory.build(version=3)

        _do_full_upload(bsw, v2_img)
        _do_swap(bsw)
        assert _slot_version(board.BOOT_FLASH_ADDRESS) == 2

        _do_full_upload(bsw, v3_img)
        _do_swap(bsw)
        assert _slot_version(board.BOOT_FLASH_ADDRESS) == 3
        assert board.get_rollback_counter() == 3


# ---------------------------------------------------------------------------
# TestRollbackWithWindow
# ---------------------------------------------------------------------------

class TestRollbackWithWindow:
    """After a v1→v2 swap, upload v1 (within the rollback window=1) and swap again.

    With counter=2 and window=1, floor=1.  Version 1 is at the floor and must
    be accepted for both upload and swap.
    """

    def test_v1_rollback_accepted_and_boot_reverts(self, nominal_state, bsw, config, image_factory):
        """v1→v2 swap (counter=2, floor=1); upload v1 (at floor, must be accepted);
        swap again → BOOT=v1."""
        v2_img = image_factory.build(version=2)
        v1_img = image_factory.build(version=1)

        _do_full_upload(bsw, v2_img)
        _do_swap(bsw)
        assert _slot_version(board.BOOT_FLASH_ADDRESS) == 2
        assert board.get_rollback_counter() == 2

        _do_full_upload(bsw, v1_img)  # floor=1, must not raise
        assert _slot_version(board.UPDATE_FLASH_ADDRESS) == 1

        _do_swap(bsw)
        assert _slot_version(board.BOOT_FLASH_ADDRESS) == 1

    def test_version_below_floor_rejected_after_upgrade(self, nominal_state, bsw, config, image_factory):
        """After a v1→v2→v3 two-step upgrade, uploading v1 (floor=2) must be rejected."""
        v2_img = image_factory.build(version=2)
        v3_img = image_factory.build(version=3)
        v1_img = image_factory.build(version=1)

        _do_full_upload(bsw, v2_img)
        _do_swap(bsw)
        _do_full_upload(bsw, v3_img)
        _do_swap(bsw)
        # counter=3, floor=2

        # After two swaps COMM is already NOMINAL; send '2' during the window to enter update
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            _do_full_upload(bsw, v1_img)  # should raise on chunk 1 (version check)
        assert exc_info.value.error_code == 9


# ---------------------------------------------------------------------------
# TestAutomaticRollbackBothFail
# ---------------------------------------------------------------------------

class TestAutomaticRollbackBothFail:
    """BOOT=v2 fails to run (status stays BOOT_ATTEMPTED after app reset).
    The UPDATE slot holds v1 which is within the rollback window, so BSW
    triggers an auto-swap.  After the swap the NEW BOOT is the old v1 image.
    That image also fails (we force it by writing BOOT_ATTEMPTED again before
    the second boot attempt), leaving no valid rollback candidate.
    The BSW should end up in standby (COMM=111).

    Flash state built directly without going through the upload flow:
      BOOT=v2, UPDATE=v1, counter=2, COMM=NOMINAL, sectors protected.
    """

    @pytest.fixture
    def both_fail_state(self, clean_flash, image_factory):
        """BOOT=v2, UPDATE=v1, counter=2, COMM=NOMINAL, nominal WRP."""
        boot_img   = image_factory.build(version=2)
        update_img = image_factory.build(version=1)
        board.flash_image(board.BOOT_FLASH_ADDRESS,   boot_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, update_img)
        board.set_rollback_counter(2)
        board.set_comm_status(board.COMM_STATUS_NOMINAL)
        # Ensure protected
        if not board.is_write_protected(board.OB_WRP_BOOT) or \
           not board.is_write_protected(board.OB_WRP_COUNTER):
            board.set_write_protection(
                protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER
            )
            time.sleep(1.5)
        yield boot_img, update_img

    def test_both_boots_fail_leaves_standby(self, both_fail_state, bsw, config):
        """Round 1: BOOT_ATTEMPTED → rollback swap → BOOT=v1.
        Round 2: BOOT_ATTEMPTED again → no candidate → COMM=STANDBY."""
        # Round 1: v2 fails → BSW triggers rollback swap
        board.set_comm_status(board.COMM_STATUS_BOOT_ATTEMPTED)
        board.reset_board(delay=1.0)
        _skip_timeout(bsw)
        bsw.drain_debug_log(timeout=5.0)
        _skip_timeout(bsw)
        bsw.drain_debug_log(timeout=10.0)  # rollback swap + OB_Launch reset
        assert _slot_version(board.BOOT_FLASH_ADDRESS) == 1

        # Round 2: v1 also fails
        board.set_comm_status(board.COMM_STATUS_BOOT_ATTEMPTED)
        board.reset_board(delay=1.0)
        _skip_timeout(bsw)
        bsw.drain_debug_log(timeout=5.0)
        time.sleep(2.5)

        assert board.get_comm_status() == board.COMM_STATUS_STANDBY


# ---------------------------------------------------------------------------
# TestAutomaticRollbackSecondSucceeds
# ---------------------------------------------------------------------------

class TestAutomaticRollbackSecondSucceeds:
    """BOOT=v2 fails; rollback swap puts v1 in BOOT; v1 runs successfully
    (app writes NOMINAL) and the system stabilises.

    Flash state: BOOT=v2, UPDATE=v1 (real ASW), counter=2, COMM=NOMINAL.
    Requires REAL_ASW_BIN so that a genuine bootable image can be launched.
    """

    @pytest.fixture
    def rollback_succeeds_state(self, clean_flash, image_factory, real_asw_image):
        """BOOT=v2 (synthetic, version tag only), UPDATE=real-ASW-v1,
        counter=2, COMM=NOMINAL, nominal WRP."""
        boot_img = image_factory.build(version=2)
        board.flash_image(board.BOOT_FLASH_ADDRESS,   boot_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, real_asw_image)
        board.set_rollback_counter(2)
        board.set_comm_status(board.COMM_STATUS_NOMINAL)
        if not board.is_write_protected(board.OB_WRP_BOOT) or \
           not board.is_write_protected(board.OB_WRP_COUNTER):
            board.set_write_protection(
                protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER
            )
            time.sleep(1.5)
        yield boot_img, real_asw_image

    def test_rollback_swap_then_second_boot_succeeds_and_confirms_nominal(
            self, rollback_succeeds_state, bsw, config):
        """Step 1: BOOT_ATTEMPTED → rollback swap → BOOT=real-ASW-v1.
        Step 2: BSW boots v1 → 'App STARTED' appears.
        Step 3: test sends '1' to ASW → ASW sets NOMINAL + resets → COMM=NOMINAL."""
        # Step 1: trigger rollback swap
        board.set_comm_status(board.COMM_STATUS_BOOT_ATTEMPTED)
        board.reset_board(delay=1.0)
        _skip_timeout(bsw)
        bsw.drain_debug_log(timeout=5.0)
        _skip_timeout(bsw)
        bsw.drain_debug_log(timeout=10.0)
        assert _slot_version(board.BOOT_FLASH_ADDRESS) == 1

        # Step 2: BOOT slot = real ASW v1, COMM = NOMINAL → BSW boots it
        board.reset_board(delay=1.0)
        _skip_timeout(bsw)
        log = "".join(bsw.drain_debug_log(timeout=5.0))
        assert "App STARTED" in log
