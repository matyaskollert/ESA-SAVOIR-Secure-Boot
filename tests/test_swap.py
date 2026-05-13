"""
test_swap.py - E2E tests for the BSW image swap path (command '3').

After a successful swap:
  - The MAIN slot contains what was previously in UPDATE.
  - The SWAP slot contains what was previously in MAIN.
  - The rollback counter is updated to the new MAIN version if it is higher.
  - The COMM status word is written to COMM_STATUS_SWAP (0xCC) to coordinate
    the two-phase swap (BSW writes it before resetting for OB change, then
    checks it on the next boot).
"""

import binascii
import struct
import time
import pytest

from helpers import board, serial_comm
from helpers.image_factory import ImageFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slot_version(address: int) -> int:
    raw = board.flash_read(address, 8)
    _crc, _magic, version = struct.unpack("<IHH", raw)
    return version


class TestSwapHappyPath:
    """Happy-path swap: SLOT_A=v1 (primary), SLOT_B=v2 (secondary), COMM=SWAP-ready,
    WRP unlocked for primary slot and PROTECTED_BSW_STATE."""

    def test_swap_performs_correctly(self, bsw, clean_flash, slot_config, image_factory, config):
        """ACK received; primary_slot flipped, counter=2, sectors re-protected."""
        primary_img = image_factory.build(version=1)
        secondary_img = image_factory.build(version=2)
        board.flash_image(slot_config.primary_address, primary_img)
        board.flash_image(slot_config.secondary_address, secondary_img)
        board.set_rollback_counter(1)
        board.set_primary_flag(slot_config.primary_flag)

        # Replicate setupSystemForImageSwap(): COMM=0xCC, unlock primary+PROTECTED_BSW_STATE
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
        )
        board.reset_board()
        bsw.send_command("3", sequence=0)
        ack = bsw.wait_for_ack(expected_sequence=0)
        assert ack is not None
        bsw.drain_debug_log(timeout=6.0)  # let the swap finish

        # After the swap the primary slot must contain v2 and the secondary v1.
        # This holds regardless of whether the BSW uses a flag-based swap
        # (flag flips, flash data unchanged) or a hardware swap (data moves,
        # flag unchanged): get_primary_slot() always resolves to the slot that
        # physically holds the new primary image.
        assert (
            _slot_version(board.get_primary_slot()) == 2
        ), "Primary slot must contain v2 after swap"
        assert (
            _slot_version(board.get_secondary_slot()) == 1
        ), "Secondary slot must contain v1 after swap"
        # Rollback counter must advance to the new primary version.
        assert (
            board.get_rollback_counter() == 2
        ), "Rollback counter must be updated to new primary version after swap"
        # New primary slot and PROTECTED_BSW_STATE must be re-protected.
        assert board.is_write_protected(
            board.get_primary_slot_ob_mask()
        ), "New primary slot must be write-protected after swap"
        assert board.is_write_protected(
            board.OB_WRP_PROTECTED_BSW_STATE
        ), "PROTECTED_BSW_STATE sector must be re-protected after swap"
        # Old primary (now secondary) must be unprotected.
        assert not board.is_write_protected(
            board.get_secondary_slot_ob_mask()
        ), "Old primary (now secondary) must be unprotected after swap"

        # Verify the BSW SWAP report persisted to flash
        report = board.get_latest_report()
        assert (
            report is not None
        ), "A SWAP report must be written after a successful swap"
        assert report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert report["outcome"] == 0
        assert report["step_flags"] == (
            board.BSW_SWAP_FLAG_SYSTEM_OK
            | board.BSW_SWAP_FLAG_VERSION_OK
            | board.BSW_SWAP_FLAG_CRC_OK
            | board.BSW_SWAP_FLAG_SIG_OK
            | board.BSW_SWAP_FLAG_COUNTER_OK
            | board.BSW_SWAP_FLAG_SLOT_FLIPPED
        )
        # The report captures primary_slot BEFORE the swap
        assert report["primary_slot"] == slot_config.primary_slot_enum


class TestSwapMainSectorStillProtected:
    """BSW must refuse swap when COMM=0xCC but primary slot (SLOT_A) is still write-protected."""

    @pytest.fixture(autouse=True)
    def setup_main_protected(self, clean_flash, slot_config, image_factory):
        """Flash primary=v1/secondary=v2, set COMM=SWAP, unprotect only PROTECTED_BSW_STATE."""
        primary_img = image_factory.build(version=1)
        secondary_img = image_factory.build(version=2)
        board.flash_image(slot_config.primary_address, primary_img)
        board.flash_image(slot_config.secondary_address, secondary_img)
        board.set_rollback_counter(1)
        board.set_primary_flag(slot_config.primary_flag)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=slot_config.primary_ob_mask,
            unprotect_mask=board.OB_WRP_PROTECTED_BSW_STATE,
        )
        yield
        board.set_write_protection(
            protect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=slot_config.secondary_ob_mask,
        )

    def test_nack_when_main_sector_still_protected(self, bsw, config):
        """COMM=SWAP but MAIN sector is still write-protected → NACK 12."""
        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 12

        # BSW writes a SWAP report (outcome=7) then resets; subsequent auto-swap
        # may add another report, so we only assert on type/outcome of the first report.
        assert board.read_all_reports()[0]["outcome"] == 7


class TestSwapBSWStateSectorStillProtected:
    """BSW must refuse swap when COMM=0xCC but PROTECTED_BSW_STATE sector is still write-protected."""

    @pytest.fixture(autouse=True)
    def setup_bsw_state_protected(self, clean_flash, slot_config, image_factory):
        """Flash primary=v1/secondary=v2, set COMM=SWAP, unprotect only primary slot."""
        primary_img = image_factory.build(version=1)
        secondary_img = image_factory.build(version=2)
        board.flash_image(slot_config.primary_address, primary_img)
        board.flash_image(slot_config.secondary_address, secondary_img)
        board.set_rollback_counter(1)
        board.set_primary_flag(slot_config.primary_flag)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=slot_config.primary_ob_mask,
        )
        yield
        board.set_write_protection(
            protect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=slot_config.secondary_ob_mask,
        )

    def test_nack_when_bsw_state_sector_still_protected(self, bsw, config):
        """COMM=SWAP but BSW_STATE sector is still write-protected → NACK 12."""
        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 12

        # BSW writes a SWAP report (outcome=7) then resets; subsequent auto-swap
        # may add another report, so we only assert on type/outcome of the first report.
        assert board.read_all_reports()[0]["outcome"] == 7


class TestSwapBothSectorsStillProtected:
    """BSW must refuse swap when COMM=0xCC but both sectors are still write-protected."""

    @pytest.fixture(autouse=True)
    def setup_both_protected(self, nominal_state):
        """Set COMM=SWAP while leaving both sectors protected (nominal WRP state)."""
        board.set_comm_status(board.COMM_STATUS_SWAP)
        yield
        board.set_comm_status(board.COMM_STATUS_NOMINAL)

    def test_nack_when_both_sectors_still_protected(self, bsw, config):
        """COMM=SWAP but both sectors still protected → NACK 12."""
        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 12


class TestSwapBadUpdateSlot:
    """BSW must reject swap when the UPDATE slot is empty, corrupt, or has a bad signature.

    checkUpdateVersion() calls imageLoad(UPDATE) which runs CRC + signature
    checks before reading the version field.
    """

    def test_nack_when_update_slot_empty(self, swap_ready_state, slot_config, bsw, config):
        """UPDATE slot erased → imageGetHeader fails → NACK (via checkUpdateVersion)."""
        board.flash_erase_slot(slot_config.secondary_address)

        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)

        # checkUpdateVersion fails (NULL header); BSW returns without reset
        report = board.get_latest_report()
        assert report is not None
        assert report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert report["outcome"] == 8
        assert report["step_flags"] == board.BSW_SWAP_FLAG_SYSTEM_OK

    def test_nack_when_update_has_bad_magic(
        self, swap_ready_state, slot_config, bsw, config, image_factory
    ):
        """UPDATE slot has wrong magic → imageGetHeader returns NULL → NACK."""
        good_img = image_factory.build(version=2)
        bad_img = ImageFactory.corrupt_magic(good_img)
        board.flash_image(slot_config.secondary_address, bad_img)

        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)

        # checkUpdateVersion fails (NULL header); BSW returns without reset
        report = board.get_latest_report()
        assert report is not None
        assert report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert report["outcome"] == 8
        assert report["step_flags"] == board.BSW_SWAP_FLAG_SYSTEM_OK

    def test_nack_when_update_has_corrupt_crc(
        self, swap_ready_state, slot_config, bsw, config, image_factory
    ):
        """UPDATE slot has corrupted CRC → imageValidate fails → NACK."""
        good_img = image_factory.build(version=2)
        bad_img = ImageFactory.corrupt_crc(good_img)
        board.flash_image(slot_config.secondary_address, bad_img)

        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)

        # checkUpdateValidity fails at CRC; BSW returns without reset
        report = board.get_latest_report()
        assert report is not None
        assert report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert report["outcome"] == 9
        assert report["step_flags"] == (
            board.BSW_SWAP_FLAG_SYSTEM_OK | board.BSW_SWAP_FLAG_VERSION_OK
        )

    def test_nack_when_update_has_invalid_signature(
        self, swap_ready_state, slot_config, bsw, config, image_factory
    ):
        """UPDATE slot CRC is valid but signature is tampered → imageLoad fails → NACK."""
        good_img = image_factory.build(version=2)
        bad_sig = ImageFactory.corrupt_signature(good_img)
        new_crc = ImageFactory._crc32_mpeg2(bad_sig[4:])
        bad_img = struct.pack("<I", new_crc) + bad_sig[4:]
        board.flash_image(slot_config.secondary_address, bad_img)

        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)

        # checkUpdateValidity fails at signature; BSW returns without reset
        report = board.get_latest_report()
        assert report is not None
        assert report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert report["outcome"] == 10
        assert report["step_flags"] == (
            board.BSW_SWAP_FLAG_SYSTEM_OK
            | board.BSW_SWAP_FLAG_VERSION_OK
            | board.BSW_SWAP_FLAG_CRC_OK
        )


class TestSwapVersionRejectionRecovery:
    """After checkUpdateVersion() rejects with NACK 9, the BSW must restore nominal state.

    setupSystemForNominal() is called: COMM ← 0xAA, MAIN and PROTECTED_BSW_STATE re-protected.
    """

    @pytest.fixture(autouse=True)
    def setup_rollback_scenario(self, clean_flash, slot_config, image_factory):
        """Counter = 5, primary = v5, secondary = v3 (below floor=4).  System in SWAP state."""
        primary_img = image_factory.build(version=5)
        secondary_img = image_factory.build(version=3)  # below floor
        board.flash_image(slot_config.primary_address, primary_img)
        board.flash_image(slot_config.secondary_address, secondary_img)
        board.set_rollback_counter(5)
        board.set_primary_flag(slot_config.primary_flag)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
        )

    def test_nack_9_on_version_below_floor(self, bsw, config):
        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 9

        # Version check rejects before swapBootWithUpdate() — BSW returns without reset
        report = board.get_latest_report()
        assert report is not None
        assert report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert report["outcome"] == 8
        assert report["step_flags"] == board.BSW_SWAP_FLAG_SYSTEM_OK


class TestSwapRollbackCounterEdges:
    """Rollback counter update edge cases in updateRollbackCounter()."""

    def test_counter_not_incremented_when_already_current(
        self, swap_ready_state, bsw, config
    ):
        """If the counter already equals the new MAIN version, it must stay unchanged."""
        # swap_ready_state: MAIN=v1, UPDATE=v2, counter=1.
        # After swap: new MAIN=v2, counter should become 2.
        # Pre-set counter = 2 so the new MAIN version == counter.
        board.set_rollback_counter(2)

        board.reset_board()
        bsw.send_command("3", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.drain_debug_log(timeout=3.0)
        time.sleep(2.0)

        # Counter was already 2 (== new MAIN version 2); must stay 2.
        assert board.get_rollback_counter() == 2

        report = board.get_latest_report()
        assert report is not None, "A SWAP report must be written after swap"
        assert report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert report["outcome"] == 0
        assert report["step_flags"] == (
            board.BSW_SWAP_FLAG_SYSTEM_OK
            | board.BSW_SWAP_FLAG_VERSION_OK
            | board.BSW_SWAP_FLAG_CRC_OK
            | board.BSW_SWAP_FLAG_SIG_OK
            | board.BSW_SWAP_FLAG_COUNTER_OK
            | board.BSW_SWAP_FLAG_SLOT_FLIPPED
        )

    def test_counter_updated_when_new_boot_is_higher(
        self, swap_ready_state, bsw, config
    ):
        """Counter must advance to the new MAIN version when it is higher."""
        # swap_ready_state already has counter=1, MAIN=v1, UPDATE=v2.
        board.reset_board()
        bsw.send_command("3", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.drain_debug_log(timeout=5.0)
        time.sleep(1.0)

        assert board.get_rollback_counter() == 2

        report = board.get_latest_report()
        assert report is not None, "A SWAP report must be written after swap"
        assert report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert report["outcome"] == 0
        assert report["step_flags"] == (
            board.BSW_SWAP_FLAG_SYSTEM_OK
            | board.BSW_SWAP_FLAG_VERSION_OK
            | board.BSW_SWAP_FLAG_CRC_OK
            | board.BSW_SWAP_FLAG_SIG_OK
            | board.BSW_SWAP_FLAG_COUNTER_OK
            | board.BSW_SWAP_FLAG_SLOT_FLIPPED
        )


class TestSwapRollbackEnforcement:
    """Rollback counter must prevent downgrade at the *swap* stage.

    checkUpdateVersion() is called during command '3'.  The UPDATE image must
    pass CRC + signature before its version is compared against the floor.
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_flash, slot_config, image_factory):
        """Counter = 10, window = 1 → floor = 9.
        Primary = v10, secondary = v8 (below floor).  System in SWAP state.
        """
        primary_img = image_factory.build(version=10)
        secondary_img = image_factory.build(version=8)
        board.flash_image(slot_config.primary_address, primary_img)
        board.flash_image(slot_config.secondary_address, secondary_img)
        board.set_rollback_counter(10)
        board.set_primary_flag(slot_config.primary_flag)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
        )

    def test_nack9_and_state_unchanged_after_rejection(self, slot_config, bsw, config):
        """Version 8 < floor 9 → NACK 9; MAIN slot and counter must be unchanged."""
        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 9
        time.sleep(1.0)

        raw = board.flash_read(slot_config.primary_address, 8)
        _crc, _magic, version = struct.unpack("<IHH", raw)
        assert (
            version == 10
        ), "Primary slot version must be unchanged after rollback rejection"
        assert (
            board.get_rollback_counter() == 10
        ), "Counter must be unchanged after rollback rejection"

        # NACK 9 is raised before swapBootWithUpdate() — BSW returns without reset
        report = board.get_latest_report()
        assert report is not None
        assert report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert report["outcome"] == 8
        assert report["step_flags"] == board.BSW_SWAP_FLAG_SYSTEM_OK


class TestSwapPrimarySlotErased:
    """Primary slot is erased but secondary slot has a valid image.

    checkUpdateVersion() and checkUpdateValidity() only inspect the secondary
    slot, so they both pass and swapMainWithUpdate() is entered.  Inside
    swapMainWithUpdate(), imageGetHeader(oldImageSlot) returns NULL.
    The BSW logs a warning but continues: it skips the MAIN→SWAP backup step
    and only performs UPDATE→MAIN, so the swap must succeed (outcome=0).
    """

    @pytest.fixture(autouse=True)
    def setup_erased_primary(self, clean_flash, slot_config, image_factory):
        """Primary slot erased, secondary=v2.  System in SWAP state."""
        secondary_img = image_factory.build(version=2)
        # primary slot left erased (no header)
        board.flash_image(slot_config.secondary_address, secondary_img)
        board.set_rollback_counter(1)
        board.set_primary_flag(slot_config.primary_flag)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
        )
        yield
        board.set_write_protection(
            protect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=slot_config.secondary_ob_mask,
        )

    def test_swap_succeeds_when_primary_header_null(self, bsw, config):
        """BSW ACKs the swap command, logs the NULL-header warning, skips the
        MAIN→SWAP backup, writes UPDATE→MAIN, and completes successfully."""
        board.reset_board()
        bsw.send_command("3", sequence=0)
        ack = bsw.wait_for_ack(expected_sequence=0)
        assert ack is not None
        log = "".join(bsw.drain_debug_log(timeout=6.0))
        assert "Primary slot image header is NULL" in log

        # Primary slot must now contain v2 (the update image).
        assert (
            _slot_version(board.get_primary_slot()) == 2
        ), "Primary slot must hold v2 after swap even when old header was NULL"

        # Rollback counter must advance to newVersion (2) since counter (1) < 2.
        assert board.get_rollback_counter() == 2

        report = board.get_latest_report()
        assert (
            report is not None
        ), "A SWAP report must be written after a successful swap"
        assert report["type"] == board.BSW_REPORT_TYPE_SWAP
        assert report["outcome"] == 0
        assert report["step_flags"] == (
            board.BSW_SWAP_FLAG_SYSTEM_OK
            | board.BSW_SWAP_FLAG_VERSION_OK
            | board.BSW_SWAP_FLAG_CRC_OK
            | board.BSW_SWAP_FLAG_SIG_OK
            | board.BSW_SWAP_FLAG_COUNTER_OK
            | board.BSW_SWAP_FLAG_SLOT_FLIPPED
        )
