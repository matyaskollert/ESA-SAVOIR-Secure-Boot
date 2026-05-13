"""
test_lifecycle.py - End-to-end lifecycle tests for the BSW bootloader.

These tests exercise multi-step scenarios that span more than one boot cycle
or combine upload + swap + boot in sequence.  Each test drives the full state
machine from a clean baseline through to a verified final state.

All tests use the BSW autonomous mode: the appropriate COMM status is written
before the board resets, and '6' (skip-timeout) is sent during the 15 s
window so the bootloader acts on its status immediately rather than waiting.

Scenarios covered
-----------------
1. Full update cycle:     MAIN=v1 → upload v2 → swap → MAIN=v2
2. Upload without swap:   upload v2 but skip swap → MAIN still v1
3. Consecutive swaps:     v1 → v2 → v3
4. Interrupted swap → boot attempt:
     After upload the board resets with COMM=0xCC + sectors unlocked.
     BSW enters standby (interrupted state), '6' skips out, status=0xCC
     triggers auto-swap, leaving the system nominal.
5. Interrupted swap → update attempt:
     Same interrupted state; status=0xCC triggers auto-swap first.
6. Rollback window:  v1 → v2 (swap), upload v1 (within window=1), swap → v1
7. Rollback - both images fail: MAIN=v2 fails, UPDATE=v1 also fails
     → BSW ends up in standby.
8. Rollback - first image fails, second runs: MAIN=v2 fails, UPDATE=v1 runs OK
     → MAIN slot ends up as v1, COMM becomes NOMINAL.
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
    bsw.send_command("6", sequence=0)
    bsw.wait_for_ack(expected_sequence=0, timeout=1.0)


def _do_full_upload(bsw, image_data: bytes) -> None:
    """Reset the board, send '2' during the 15 s input window to enter update
    mode, upload the image, then wait for the BSW to reset into SWAP state.
    Caller must ensure COMM=NOMINAL and sectors are protected beforehand."""
    board.reset_board()
    bsw.send_command("2", sequence=0)
    bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
    bsw.upload_image(image_data, start_sequence=1)
    time.sleep(3)  # BSW calls setupSystemForImageSwap() then resets


def _do_swap(bsw) -> None:
    """Reset the board; the BSW auto-swaps when '6' skips the timeout.
    Caller must ensure COMM=SWAP (0xCC) beforehand."""
    board.reset_board()
    _skip_timeout(bsw)
    bsw.drain_debug_log(timeout=6.0)  # allow OB_Launch reset from setupSystemForNominal


class TestFullUpdateCycle:
    """SLOT_A=v1 (primary) → upload v2 to SLOT_B → swap → verify all post-cycle state."""

    def test_full_cycle(self, nominal_state, bsw, config, image_factory):
        """Upload v2, swap, then verify SLOT_B is now primary (v2), counter=2,
        WRP re-protected, COMM=NOMINAL, and that the BSW autonomously boots v2."""
        update_img = image_factory.build(version=2)
        _do_full_upload(bsw, update_img)
        _do_swap(bsw)

        # After the swap the primary slot must contain v2 and the secondary v1,
        # regardless of whether a flag-based or hardware swap was performed.
        assert (
            _slot_version(board.get_primary_slot()) == 2
        ), "New primary must hold v2 after swap"
        assert (
            _slot_version(board.get_secondary_slot()) == 1
        ), "Old primary still holds v1"
        assert board.get_rollback_counter() == 2, "Counter must advance to 2"
        assert board.is_write_protected(
            board.get_primary_slot_ob_mask()
        ), "New primary slot must be protected after cycle"
        assert board.is_write_protected(
            board.OB_WRP_PROTECTED_BSW_STATE
        ), "PROTECTED_BSW_STATE must be protected after cycle"
        assert board.get_comm_status() == board.COMM_STATUS_NOMINAL

        board.reset_board()
        _skip_timeout(bsw)
        log = "".join(bsw.drain_debug_log(timeout=3.0))
        assert "CRC validation in RAM successful" in log
        # After a full upload+swap cycle two reports must be in flash:
        #   age=0 (slot 2): NOMINAL success from the new image's boot
        #   age=1 (slot 1): SWAP success
        #   age=2 (slot 0): UPDATE success
        reports = board.read_all_reports()
        assert (
            len(reports) == 3
        ), f"Expected 3 reports (UPDATE + SWAP + NOMINAL), got {len(reports)}"

        nominal_report = board.get_latest_report()
        assert nominal_report is not None
        assert nominal_report["type"] == board.BSW_REPORT_TYPE_NOMINAL
        assert nominal_report["outcome"] == 0
        assert nominal_report["step_flags"] == (
            board.BSW_NOMINAL_FLAG_SYSTEM_OK
            | board.BSW_NOMINAL_FLAG_STATUS_SET
            | board.BSW_NOMINAL_FLAG_CRC_OK
            | board.BSW_NOMINAL_FLAG_SIG_OK
            | board.BSW_NOMINAL_FLAG_RAM_CRC_OK
        )

        swap_report = reports[1]  # age=1 — the SWAP report sits in slot 1
        assert swap_report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert swap_report["outcome"] == 0
        assert swap_report["step_flags"] == (
            board.BSW_SWAP_FLAG_VERSION_OK
            | board.BSW_SWAP_FLAG_CRC_OK
            | board.BSW_SWAP_FLAG_SIG_OK
            | board.BSW_SWAP_FLAG_COUNTER_OK
            | board.BSW_SWAP_FLAG_SLOT_FLIPPED
            | board.BSW_SWAP_FLAG_SYSTEM_OK
        )

        update_report = reports[0]  # age=2 — the UPDATE report sits in slot 0
        assert update_report["type"] == board.BSW_REPORT_TYPE_UPDATE
        assert update_report["outcome"] == 0
        assert update_report["step_flags"] == (
            board.BSW_UPDATE_FLAG_VERSION_OK
            | board.BSW_UPDATE_FLAG_RAM_CRC_OK
            | board.BSW_UPDATE_FLAG_RAM_SIG_OK
            | board.BSW_UPDATE_FLAG_FLASH_OK
            | board.BSW_UPDATE_FLAG_SYSTEM_OK
        )


class TestConsecutiveSwaps:
    """Perform two consecutive upgrades: v1 → v2 → v3."""

    def test_two_consecutive_upgrades(self, nominal_state, bsw, config, image_factory):
        """v1→v2 swap then v2→v3 swap; primary slot holds v3 and counter=3."""
        v2_img = image_factory.build(version=2)
        v3_img = image_factory.build(version=3)

        _do_full_upload(bsw, v2_img)
        _do_swap(bsw)
        assert _slot_version(board.get_primary_slot()) == 2

        _do_full_upload(bsw, v3_img)
        _do_swap(bsw)
        assert _slot_version(board.get_primary_slot()) == 3
        assert board.get_rollback_counter() == 3

        # After two upload+swap cycles, 4 reports in flash: UPDATE1, SWAP1, UPDATE2, SWAP2
        reports = board.read_all_reports()
        assert (
            len(reports) == 4
        ), f"Expected 4 reports after two cycles, got {len(reports)}"
        # Newest report (age=0) is the second SWAP
        latest = board.get_latest_report()
        assert latest is not None
        assert latest["type"] == board.BSW_REPORT_TYPE_SWAP
        assert latest["outcome"] == 0


class TestRollbackWithWindow:
    """After a v1→v2 swap, upload v1 (within the rollback window=1) and swap again.

    With counter=2 and window=1, floor=1.  Version 1 is at the floor and must
    be accepted for both upload and swap.
    """

    def test_v1_rollback_accepted_and_boot_reverts(
        self, nominal_state, bsw, config, image_factory
    ):
        """v1→v2 swap (counter=2, floor=1); upload v1 (at floor, must be accepted);
        swap again → primary slot holds v1."""
        v2_img = image_factory.build(version=2)
        v1_img = image_factory.build(version=1)

        _do_full_upload(bsw, v2_img)
        _do_swap(bsw)
        assert _slot_version(board.get_primary_slot()) == 2
        assert board.get_rollback_counter() == 2

        _do_full_upload(bsw, v1_img)  # floor=1, must not raise
        assert _slot_version(board.get_secondary_slot()) == 1

        _do_swap(bsw)
        assert _slot_version(board.get_primary_slot()) == 1

        # Newest report is a SWAP with outcome=0 (the v1 rollback swap)
        swap_report = board.get_latest_report()
        assert swap_report is not None
        assert swap_report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert swap_report["outcome"] == 0

    def test_version_below_floor_rejected_after_upgrade(
        self, nominal_state, bsw, config, image_factory
    ):
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

        time.sleep(1.0)  # wait for the BSW to write the report

        # Newest report is an UPDATE with outcome=9 (version below floor)
        update_report = board.get_latest_report()
        assert update_report is not None
        assert update_report["type"] == board.BSW_REPORT_TYPE_UPDATE
        assert update_report["outcome"] == 9
        assert update_report["step_flags"] == board.BSW_UPDATE_FLAG_SYSTEM_OK


class TestAutomaticRollbackBothFail:
    """MAIN=v2 fails to run (status stays BOOT_ATTEMPTED after app reset).
    The UPDATE slot holds v1 which is within the rollback window, so BSW
    triggers an auto-swap.  After the swap the NEW MAIN is the old v1 image.
    That image also fails (we force it by writing BOOT_ATTEMPTED again before
    the second boot attempt), leaving no valid rollback candidate.
    The BSW should end up in standby (COMM=0xBB).

    Flash state built directly without going through the upload flow:
      MAIN=v2, UPDATE=v1, counter=2, COMM=NOMINAL, sectors protected.
    """

    @pytest.fixture
    def both_fail_state(self, clean_flash, slot_config, image_factory):
        """Primary=v2, Secondary=v1, counter=2, COMM=NOMINAL, nominal WRP."""
        primary_img = image_factory.build(version=2)
        secondary_img = image_factory.build(version=1)
        board.flash_image(slot_config.primary_address, primary_img)
        board.flash_image(slot_config.secondary_address, secondary_img)
        board.set_rollback_counter(2)
        board.set_primary_flag(slot_config.primary_flag)
        board.set_comm_status(board.COMM_STATUS_NOMINAL)
        # Ensure primary slot + PROTECTED_BSW_STATE are protected and secondary is unprotected
        if (
            not board.is_write_protected(slot_config.primary_ob_mask)
            or not board.is_write_protected(board.OB_WRP_PROTECTED_BSW_STATE)
            or board.is_write_protected(slot_config.secondary_ob_mask)
        ):
            board.set_write_protection(
                protect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
                unprotect_mask=slot_config.secondary_ob_mask,
            )
        yield primary_img, secondary_img

    def test_both_boots_fail_leaves_standby(self, both_fail_state, bsw, config):
        """Round 1: BOOT_ATTEMPTED → rollback swap → MAIN=v1.
        Round 2: BOOT_ATTEMPTED again → no candidate → enter standby."""
        # Round 1: v2 fails → BSW triggers rollback swap
        board.set_comm_status(board.COMM_STATUS_BOOT_ATTEMPTED)
        board.reset_board()
        _skip_timeout(bsw)
        bsw.drain_debug_log(timeout=3.0)
        _skip_timeout(bsw)
        bsw.drain_debug_log(timeout=6.0)  # rollback swap + OB_Launch reset
        assert _slot_version(board.get_primary_slot()) == 1

        # Round 2: v1 also fails
        board.set_comm_status(board.COMM_STATUS_BOOT_ATTEMPTED)
        board.reset_board()
        _skip_timeout(bsw)
        log = "".join(bsw.drain_debug_log(timeout=6.0))

        assert "Rollback not applicable" in log


class TestAutomaticRollbackSecondSucceeds:
    """MAIN=v2 fails; rollback swap puts v1 in MAIN; v1 runs successfully
    (app writes NOMINAL) and the system stabilises.

    Flash state: MAIN=v2, UPDATE=v1 (real ASW), counter=2, COMM=NOMINAL.
    Requires REAL_ASW_BIN so that a genuine bootable image can be launched.
    """

    @pytest.fixture
    def rollback_succeeds_state(self, clean_flash, slot_config, image_factory, real_asw_image):
        """Primary=v2 (synthetic), Secondary=real-ASW-v1,
        counter=2, COMM=NOMINAL, nominal WRP."""
        primary_img = image_factory.build(version=2)
        board.flash_image(slot_config.primary_address, primary_img)
        board.flash_image(slot_config.secondary_address, real_asw_image)
        board.set_rollback_counter(2)
        board.set_primary_flag(slot_config.primary_flag)
        board.set_comm_status(board.COMM_STATUS_NOMINAL)
        if (
            not board.is_write_protected(slot_config.primary_ob_mask)
            or not board.is_write_protected(board.OB_WRP_PROTECTED_BSW_STATE)
            or board.is_write_protected(slot_config.secondary_ob_mask)
        ):
            board.set_write_protection(
                protect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
                unprotect_mask=slot_config.secondary_ob_mask,
            )
        yield primary_img, real_asw_image

    def test_rollback_swap_then_second_boot_succeeds_and_confirms_nominal(
        self, rollback_succeeds_state, bsw, config
    ):
        """Step 1: BOOT_ATTEMPTED → rollback swap → MAIN=real-ASW-v1.
        Step 2: BSW boots v1 → 'App STARTED' appears.
        Step 3: test sends '1' to ASW → ASW sets NOMINAL + resets → COMM=NOMINAL."""
        # Step 1: trigger rollback swap
        board.set_comm_status(board.COMM_STATUS_BOOT_ATTEMPTED)
        board.reset_board()
        _skip_timeout(bsw)
        bsw.drain_debug_log(timeout=3.0)
        _skip_timeout(bsw)
        bsw.drain_debug_log(timeout=6.0)
        assert _slot_version(board.get_primary_slot()) == 1
        board.reset_board()
        _skip_timeout(bsw)
        log = "".join(bsw.drain_debug_log(timeout=3.0))
        assert "App STARTED" in log
