"""
test_update.py – E2E tests for the BSW firmware update path (command '2').

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
        self, nominal_state, bsw, config, image_factory
    ):
        """Upload must complete without NACK; SLOT_B slot must have correct header and bytes."""
        update_img = image_factory.build(version=2)
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(update_img, start_sequence=1, verbose=True)

        log = "".join(bsw.drain_debug_log(timeout=2.0))

        assert "Writing to flash" in log
        assert "Flash write complete" in log

        hdr = _read_header_from_slot(board.SLOT_B_FLASH_ADDRESS)
        assert hdr["magic"] == 0xABCD
        assert hdr["version"] == 2
        flash_content = board.flash_read(board.SLOT_B_FLASH_ADDRESS, len(update_img))
        assert flash_content == update_img


class TestUpdateVersionTooLow:
    """BSW must reject an image whose version is below the rollback floor."""

    @pytest.fixture(autouse=True)
    def setup_counter(self, clean_flash, image_factory):
        """Plant a version-5 image in BOOT and set the counter to 5.
        Rollback window = 1, so the lowest allowed version = 4.
        An image at version 3 must be rejected.
        """
        boot_img = image_factory.build(version=5)
        board.flash_image(board.SLOT_A_FLASH_ADDRESS, boot_img)
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

        # Send first chunk – this is where BSW inspects the version
        chunk = old_img[:256]
        bsw.send_data_chunk(chunk, sequence=2)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=2)
        assert exc_info.value.error_code == 9

    def test_version_at_floor_is_accepted(self, bsw, config, image_factory):
        """A version-4 image (floor=4) must be accepted."""
        floor_img = image_factory.build(version=4)
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(floor_img, start_sequence=1)  # should not raise


class TestUpdateUnprotectedBootSector:
    """BSW must reject the update command when the BOOT sector is unprotected."""

    @pytest.fixture(autouse=True)
    def setup_boot_unprotected(self, nominal_state):
        """Temporarily remove write-protection from the BOOT sector."""
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_SLOT_A,
        )
        yield
        board.set_write_protection(
            protect_mask=board.OB_WRP_SLOT_A | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=board.OB_WRP_SLOT_B,
        )

    def test_nack_when_boot_sector_unprotected(self, bsw, config):
        """BSW must refuse to update if checkSystemForUpdate() fails."""
        board.reset_board()
        bsw.send_command("2", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 10


class TestUpdateUnprotectedCounterSector:
    """BSW must reject the update command when the COUNTER sector is unprotected."""

    @pytest.fixture(autouse=True)
    def setup_counter_unprotected(self, nominal_state):
        """Temporarily remove write-protection from the COUNTER sector."""
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_PROTECTED_BSW_STATE,
        )
        yield
        board.set_write_protection(
            protect_mask=board.OB_WRP_SLOT_A | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=board.OB_WRP_SLOT_B,
        )

    def test_nack_and_sectors_reprotected(self, bsw, config):
        """BSW must NACK 10 and then re-protect both sectors via setupSystemForNominal()."""
        board.reset_board()
        bsw.send_command("2", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 10
        time.sleep(1.0)
        assert board.is_write_protected(board.OB_WRP_SLOT_A)
        assert board.is_write_protected(board.OB_WRP_PROTECTED_BSW_STATE)


class TestUpdateSectorProtectedDuringUpdate:
    """BSW must reject update when UPDATE sector is write-protected.

    This is the 'should never happen' branch
    (checkSystemForUpdate: 'Cannot update with UPDATE protected').
    """

    @pytest.fixture(autouse=True)
    def setup_update_protected(self, nominal_state):
        # Protect SLOT_B (secondary) in addition to the already-protected SLOT_A+PROTECTED_BSW_STATE
        board.set_write_protection(
            protect_mask=board.OB_WRP_SLOT_A
            | board.OB_WRP_PROTECTED_BSW_STATE
            | board.OB_WRP_SLOT_B,
        )
        yield
        board.set_write_protection(
            protect_mask=board.OB_WRP_SLOT_A | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=board.OB_WRP_SLOT_B,
        )

    def test_nack_and_log_mentions_update_protected(self, bsw, config):
        """BSW must NACK 10 and log that the UPDATE sector is protected."""
        board.reset_board()
        bsw.send_command("2", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 10


class TestUpdateStateAfterSuccess:
    """After a successful upload the system must be in swap-ready state.

    setupSystemForImageSwap() is called before the reset:
      - COMM word = 0xCC (COMM_STATUS_SWAP)
      - BOOT (sector 5) and COUNTER (sector 9) write-protection must be lifted
    """

    def test_system_state_after_successful_upload(
        self, nominal_state, bsw, config, image_factory
    ):
        """After upload: COMM=SWAP, BOOT+COUNTER unlocked, SLOT_B slot has correct version."""
        update_img = image_factory.build(version=2)
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(update_img, start_sequence=1)
        time.sleep(2.5)  # allow OB_Launch reset from setupSystemForImageSwap

        assert board.get_comm_status() == board.COMM_STATUS_SWAP
        assert not board.is_write_protected(
            board.OB_WRP_SLOT_A
        ), "SLOT_A sector must be unlocked after upload"
        assert not board.is_write_protected(
            board.OB_WRP_PROTECTED_BSW_STATE
        ), "PROTECTED_BSW_STATE sector must be unlocked after upload"
        hdr = _read_header_from_slot(board.SLOT_B_FLASH_ADDRESS)
        assert hdr["version"] == 2


class TestRollbackPrevention:
    """The rollback counter must prevent downgrades beyond the allowed window."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_flash, image_factory):
        """Counter = 10, window = 1 → floor = 9.  Upload version 8 → should fail."""
        boot_img = image_factory.build(version=10)
        board.flash_image(board.SLOT_A_FLASH_ADDRESS, boot_img)
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
