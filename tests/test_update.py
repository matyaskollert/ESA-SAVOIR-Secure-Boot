"""
test_update.py – E2E tests for the BSW firmware update path (command '2').

Flow under test:
  1. Send '2' command  →  BSW prepares for update and ACKs.
  2. Upload image via START / DATA_CHUNK / END sequence.
  3. Reset board and verify the UPDATE flash slot contains the new image.
"""

import struct
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


# ---------------------------------------------------------------------------
# TestUpdateHappyPath
# ---------------------------------------------------------------------------

class TestUpdateHappyPath:
    """Upload a valid version-2 image and verify it lands in the UPDATE slot."""

    def test_upload_complete(self, nominal_state, bsw, config, image_factory):
        """Full upload sequence must complete without NACK."""
        update_img = image_factory.build(version=2)
        board.reset_board(delay=1.0)

        # Command: enter update mode
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)

        # Upload
        bsw.upload_image(update_img, start_sequence=1, verbose=True)

    def test_update_slot_contains_correct_magic(self, nominal_state, bsw, config, image_factory):
        """After upload the UPDATE slot header must have the correct magic number."""
        update_img = image_factory.build(version=2)
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(update_img, start_sequence=1)

        hdr = _read_header_from_slot(board.UPDATE_FLASH_ADDRESS)
        assert hdr["magic"] == 0xABCD

    def test_update_slot_contains_correct_version(self, nominal_state, bsw, config, image_factory):
        """After upload the UPDATE slot must report version 2."""
        update_img = image_factory.build(version=2)
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(update_img, start_sequence=1)

        hdr = _read_header_from_slot(board.UPDATE_FLASH_ADDRESS)
        assert hdr["version"] == 2

    def test_update_raw_bytes_match_image(self, nominal_state, bsw, config, image_factory):
        """Raw flash content of the UPDATE slot must equal the uploaded image."""
        update_img = image_factory.build(version=2)
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(update_img, start_sequence=1)

        flash_content = board.flash_read(board.UPDATE_FLASH_ADDRESS, len(update_img))
        assert flash_content == update_img


# ---------------------------------------------------------------------------
# TestUpdateVersionTooLow
# ---------------------------------------------------------------------------

class TestUpdateVersionTooLow:
    """BSW must reject an image whose version is below the rollback floor."""

    @pytest.fixture(autouse=True)
    def setup_counter(self, clean_flash, image_factory):
        """Plant a version-5 image in BOOT and set the counter to 5.
        Rollback window = 1, so the lowest allowed version = 4.
        An image at version 3 must be rejected.
        """
        boot_img = image_factory.build(version=5)
        board.flash_image(board.BOOT_FLASH_ADDRESS, boot_img)
        board.set_rollback_counter(5)

    def test_nack_on_version_below_floor(self, bsw, config, image_factory):
        """A version-3 image (floor=4) must be rejected with error code 9."""
        old_img = image_factory.build(version=3)
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
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
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(floor_img, start_sequence=1)  # should not raise


# ---------------------------------------------------------------------------
# TestUpdateSystemNotConfigured
# ---------------------------------------------------------------------------

class TestUpdateSystemNotConfigured:
    """BSW must reject the update command when option bytes are wrong."""

    @pytest.fixture(autouse=True)
    def setup_wrong_ob(self, nominal_state):
        """Unprotect the BOOT sector so checkSystemForUpdate() fails.
        (The BSW expects BOOT+COUNTER to be protected during update mode.)
        """
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT,
        )
        import time; time.sleep(1.5)
        yield
        board.set_write_protection(protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER)
        import time; time.sleep(1.5)

    def test_nack_when_update_sector_protected(self, bsw, config):
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        assert exc_info.value.error_code == 10
