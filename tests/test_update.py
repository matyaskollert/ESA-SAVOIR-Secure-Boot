"""
test_update.py - E2E tests for the BSW firmware update path (command '2').

Flow under test:
  1. Send '2' command  →  BSW prepares for update and ACKs.
  2. Upload image via START / DATA_CHUNK / END sequence.
  3. Reset board and verify the UPDATE flash slot contains the new image.
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


def _read_header_from_slot(address: int) -> dict:
    """Read the first 12 bytes of a slot and return parsed header fields."""
    data = board.flash_read(address, 12)
    crc, magic, version, size = struct.unpack("<IHH I", data)
    return {"crc": crc, "magic": magic, "version": version, "size": size}


class TestUpdateHappyPath:
    """Upload a valid version-2 image and verify it lands in the SLOT_B slot."""

    def test_upload_completes_and_update_slot_correct(
        self, nominal_state, slot_config, bsw, config, image_factory
    ):
        """Upload must complete without NACK; secondary slot must have correct header and bytes."""
        update_img = image_factory.build(version=2)
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(update_img, start_sequence=1, verbose=True)

        log = "".join(bsw.drain_debug_log(timeout=2.0))

        assert "Writing to flash" in log
        assert "Flash write complete" in log

        hdr = _read_header_from_slot(slot_config.secondary_address)
        assert hdr["magic"] == 0xABCD
        assert hdr["version"] == 2
        flash_content = board.flash_read(slot_config.secondary_address, len(update_img))
        assert flash_content == update_img

        # Verify the BSW report persisted to flash
        report = board.get_latest_report()
        assert (
            report is not None
        ), "An UPDATE report must be written after a successful upload"
        assert report["type"] == board.BSW_REPORT_TYPE_UPDATE
        assert report["outcome"] == 0
        assert report["step_flags"] == (
            board.BSW_UPDATE_FLAG_SYSTEM_OK
            | board.BSW_UPDATE_FLAG_VERSION_OK
            | board.BSW_UPDATE_FLAG_RAM_CRC_OK
            | board.BSW_UPDATE_FLAG_RAM_SIG_OK
            | board.BSW_UPDATE_FLAG_FLASH_OK
        )
        assert report["primary_slot"] == slot_config.primary_slot_enum


class TestUpdateVersionTooLow:
    """BSW must reject an image whose version is below the rollback floor."""

    @pytest.fixture(autouse=True)
    def setup_counter(self, clean_flash, slot_config, image_factory):
        """Plant a version-5 image in the primary slot and set the counter to 5.
        Rollback window = 1, so the lowest allowed version = 4.
        An image at version 3 must be rejected.
        """
        boot_img = image_factory.build(version=5)
        board.flash_image(slot_config.primary_address, boot_img)
        board.set_rollback_counter(5)

    def test_nack_on_version_below_floor(self, bsw, config, image_factory):
        """A version-3 image (floor=4) must be rejected with error code 9."""
        old_img = image_factory.build(version=3)
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)

        # START the upload (BSW reads version from first chunk)
        bsw.send_start_upload(len(old_img), sequence=1)
        bsw.wait_for_ack(expected_sequence=1)

        # Send first chunk - this is where BSW inspects the version
        chunk = old_img[:256]
        bsw.send_data_chunk(chunk, sequence=2)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=2)
        assert exc_info.value.error_code == 9

        time.sleep(1.0)  # allow time for BSW to write report after NACK

        # BSW must write an UPDATE report recording the version rejection
        report = board.get_latest_report()
        assert (
            report is not None
        ), "An UPDATE report must be written on version rejection"
        assert report["type"] == board.BSW_REPORT_TYPE_UPDATE
        assert report["outcome"] == 9
        assert (
            report["step_flags"] == board.BSW_UPDATE_FLAG_SYSTEM_OK
        ), "Only SYSTEM_OK set when version check fails"

    def test_version_at_floor_is_accepted(self, bsw, config, image_factory):
        """A version-4 image (floor=4) must be accepted."""
        floor_img = image_factory.build(version=4)
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(floor_img, start_sequence=1)  # should not raise

        time.sleep(3.0)  # allow time for BSW to write report after NACK

        # Verify that the UPDATE report shows a successful upload
        report = board.get_latest_report()
        assert report is not None
        assert report["type"] == board.BSW_REPORT_TYPE_UPDATE
        assert report["outcome"] == 0
        assert report["step_flags"] == (
            board.BSW_UPDATE_FLAG_SYSTEM_OK
            | board.BSW_UPDATE_FLAG_VERSION_OK
            | board.BSW_UPDATE_FLAG_RAM_CRC_OK
            | board.BSW_UPDATE_FLAG_RAM_SIG_OK
            | board.BSW_UPDATE_FLAG_FLASH_OK
        )


class TestUpdateUnprotectedMainSector:
    """BSW must reject the update command when the MAIN sector is unprotected."""

    @pytest.fixture(autouse=True)
    def setup_main_unprotected(self, nominal_state, slot_config):
        """Temporarily remove write-protection from the MAIN sector."""
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=slot_config.primary_ob_mask,
        )
        yield
        board.set_write_protection(
            protect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=slot_config.secondary_ob_mask,
        )

    def test_nack_when_main_sector_unprotected(self, bsw, config):
        """BSW must refuse to update if checkSystemForUpdate() fails."""
        board.reset_board()
        bsw.send_command("2", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 10

        # BSW writes an UPDATE report (outcome=15) before calling setupSystemForUpdate()
        report = board.get_latest_report()
        assert (
            report is not None
        ), "An UPDATE report must be written on system check failure"
        assert report["type"] == board.BSW_REPORT_TYPE_UPDATE
        assert report["outcome"] == 15
        assert report["step_flags"] == 0


class TestUpdateUnprotectedBSWStateSector:
    """BSW must reject the update command when the PROTECTED_BSW_STATE sector is unprotected."""

    @pytest.fixture(autouse=True)
    def setup_bsw_state_unprotected(self, nominal_state, slot_config):
        """Temporarily remove write-protection from the PROTECTED_BSW_STATE sector."""
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_PROTECTED_BSW_STATE,
        )
        yield
        board.set_write_protection(
            protect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=slot_config.secondary_ob_mask,
        )

    def test_nack_and_sectors_reprotected(self, slot_config, bsw, config):
        """BSW must NACK 10 and then re-protect both sectors via setupSystemForNominal()."""
        board.reset_board()
        bsw.send_command("2", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 10
        time.sleep(1.0)
        assert board.is_write_protected(slot_config.primary_ob_mask)
        assert board.is_write_protected(board.OB_WRP_PROTECTED_BSW_STATE)

        # BSW writes an UPDATE report (outcome=15) before calling setupSystemForUpdate()
        report = board.get_latest_report()
        assert (
            report is not None
        ), "An UPDATE report must be written on system check failure"
        assert report["type"] == board.BSW_REPORT_TYPE_UPDATE
        assert report["outcome"] == 15
        assert report["step_flags"] == 0


class TestUpdateSectorProtectedDuringUpdate:
    """BSW must reject update when UPDATE sector is write-protected.

    This is the 'should never happen' branch
    (checkSystemForUpdate: 'Cannot update with UPDATE protected').
    """

    @pytest.fixture(autouse=True)
    def setup_update_protected(self, nominal_state, slot_config):
        # Protect secondary slot in addition to the already-protected primary+PROTECTED_BSW_STATE
        board.set_write_protection(
            protect_mask=slot_config.primary_ob_mask
            | board.OB_WRP_PROTECTED_BSW_STATE
            | slot_config.secondary_ob_mask,
        )
        yield
        board.set_write_protection(
            protect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=slot_config.secondary_ob_mask,
        )

    def test_nack_and_log_mentions_update_protected(self, bsw, config):
        """BSW must NACK 10 and log that the UPDATE sector is protected."""
        board.reset_board()
        bsw.send_command("2", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 10

        # BSW writes an UPDATE report (outcome=15) before calling setupSystemForUpdate()
        report = board.get_latest_report()
        assert (
            report is not None
        ), "An UPDATE report must be written on system check failure"
        assert report["type"] == board.BSW_REPORT_TYPE_UPDATE
        assert report["outcome"] == 15
        assert report["step_flags"] == 0


class TestUpdateStateAfterSuccess:
    """After a successful upload the system must be in swap-ready state.

    setupSystemForImageSwap() is called before the reset:
      - COMM word = 0xCC (COMM_STATUS_SWAP)
      - MAIN (sector 5) and PROTECTED_BSW_STATE (sector 9) write-protection must be lifted
    """

    def test_system_state_after_successful_upload(
        self, nominal_state, slot_config, bsw, config, image_factory
    ):
        """After upload: COMM=SWAP, primary slot + PROTECTED_BSW_STATE unlocked, secondary slot has correct version."""
        update_img = image_factory.build(version=2)
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(update_img, start_sequence=1)
        time.sleep(3.5)  # allow OB_Launch reset from setupSystemForImageSwap

        assert board.get_comm_status() == board.COMM_STATUS_SWAP
        assert not board.is_write_protected(
            slot_config.primary_ob_mask
        ), "Primary slot sector must be unlocked after upload"
        assert not board.is_write_protected(
            board.OB_WRP_PROTECTED_BSW_STATE
        ), "PROTECTED_BSW_STATE sector must be unlocked after upload"
        hdr = _read_header_from_slot(slot_config.secondary_address)
        assert hdr["version"] == 2

        # The UPDATE report must be in flash (written before setupSystemForImageSwap reset)
        report = board.get_latest_report()
        assert report is not None
        assert report["type"] == board.BSW_REPORT_TYPE_UPDATE
        assert report["outcome"] == 0
        assert report["step_flags"] == (
            board.BSW_UPDATE_FLAG_SYSTEM_OK
            | board.BSW_UPDATE_FLAG_VERSION_OK
            | board.BSW_UPDATE_FLAG_RAM_CRC_OK
            | board.BSW_UPDATE_FLAG_RAM_SIG_OK
            | board.BSW_UPDATE_FLAG_FLASH_OK
        )


class TestRollbackPrevention:
    """The rollback counter must prevent downgrades beyond the allowed window."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_flash, slot_config, image_factory):
        """Counter = 10, window = 1 → floor = 9.  Upload version 8 → should fail."""
        boot_img = image_factory.build(version=10)
        board.flash_image(slot_config.primary_address, boot_img)
        board.set_rollback_counter(10)

    def test_nack9_and_counter_unchanged_after_rejection(
        self, bsw, config, image_factory
    ):
        """Version 8 < floor 9 → NACK 9; counter must remain unchanged."""
        old_img = image_factory.build(version=8)
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.send_start_upload(len(old_img), sequence=1)
        bsw.wait_for_ack(expected_sequence=1)
        bsw.send_data_chunk(old_img[:256], sequence=2)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=2)
        assert exc_info.value.error_code == 9
        assert board.get_rollback_counter() == 10  # must be unchanged

    def test_version_at_floor_is_accepted(self, bsw, config, image_factory):
        """Version = floor (9) must be accepted without NACK."""
        floor_img = image_factory.build(version=9)
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(floor_img, start_sequence=1)  # must not raise


class TestRollbackCounterBoundary:
    """Verify the rollback floor clamps to 0 when counter ≤ ROLLBACK_WINDOW (=1)."""

    def test_version_1_accepted_when_counter_is_0(
        self, clean_flash, bsw, config, image_factory
    ):
        """Counter = 0 → floor = 0 → any version including 0 is accepted."""
        board.set_rollback_counter(0)
        update_img = image_factory.build(version=1)

        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        # Must not raise
        bsw.upload_image(update_img, start_sequence=1)

    def test_version_1_accepted_when_counter_equals_window(
        self, clean_flash, bsw, config, image_factory
    ):
        """Counter = 1 (= ROLLBACK_WINDOW) → floor = 0 → version 1 is accepted."""
        board.set_rollback_counter(1)
        update_img = image_factory.build(version=1)

        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(update_img, start_sequence=1)

    def test_version_below_floor_rejected_when_counter_gt_window(
        self, clean_flash, bsw, config, image_factory
    ):
        """Counter = 3 → floor = 2 → version 1 must be rejected."""
        board.set_rollback_counter(3)
        old_img = image_factory.build(version=1)

        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.send_start_upload(len(old_img), sequence=1)
        bsw.wait_for_ack(expected_sequence=1)
        bsw.send_data_chunk(old_img[:256], sequence=2)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=2)
        assert exc_info.value.error_code == 9
