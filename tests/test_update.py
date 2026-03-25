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

    def test_upload_completes_and_update_slot_correct(self, nominal_state, bsw, config, image_factory):
        """Upload must complete without NACK; UPDATE slot must have correct header and bytes."""
        update_img = image_factory.build(version=2)
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        import time; time.sleep(0.5)  # allow BSW to prepare for upload
        bsw.upload_image(update_img, start_sequence=1, verbose=True)

        log = "".join(bsw.drain_debug_log(timeout=3.0))

        assert "Writing to flash" in log
        assert "Flash write complete" in log

        hdr = _read_header_from_slot(board.UPDATE_FLASH_ADDRESS)
        assert hdr["magic"]   == 0xABCD
        assert hdr["version"] == 2
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

        import time; time.sleep(0.5)  # allow BSW to prepare for upload

        # START the upload (BSW reads version from first chunk)
        bsw.send_start_upload(len(old_img), sequence=1)
        bsw.wait_for_ack(expected_sequence=1)

        import time; time.sleep(0.5)

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
        import time; time.sleep(0.5)  # allow BSW to prepare for upload
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


# ---------------------------------------------------------------------------
# TestUpdateCounterSectorUnprotected
# ---------------------------------------------------------------------------

class TestUpdateCounterSectorUnprotected:
    """BSW must reject update when COUNTER sector is unprotected (BOOT is still ok).

    checkSystemForUpdate() requires both BOOT and COUNTER to be write-protected.
    """

    @pytest.fixture(autouse=True)
    def setup_counter_unprotected(self, nominal_state):
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_COUNTER,
        )
        import time; time.sleep(1.5)
        yield
        board.set_write_protection(protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER)
        import time; time.sleep(1.5)

    def test_nack_and_sectors_reprotected(self, bsw, config):
        """BSW must NACK 10 and then re-protect both sectors via setupSystemForNominal()."""
        import time
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        assert exc_info.value.error_code == 10
        time.sleep(2.5)
        assert board.is_write_protected(board.OB_WRP_BOOT)
        assert board.is_write_protected(board.OB_WRP_COUNTER)


# ---------------------------------------------------------------------------
# TestUpdateSectorProtectedDuringUpdate
# ---------------------------------------------------------------------------

class TestUpdateSectorProtectedDuringUpdate:
    """BSW must reject update when UPDATE sector is write-protected.

    This is the 'should never happen' branch
    (checkSystemForUpdate: 'Cannot update with UPDATE protected').
    """

    @pytest.fixture(autouse=True)
    def setup_update_protected(self, nominal_state):
        # Protect the UPDATE sector in addition to the already-protected BOOT+COUNTER
        board.set_write_protection(
            protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER | (1 << 6),
        )
        import time; time.sleep(1.5)
        yield
        board.set_write_protection(
            protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER,
            unprotect_mask=(1 << 6),
        )
        import time; time.sleep(1.5)

    def test_nack_and_log_mentions_update_protected(self, bsw, config):
        """BSW must NACK 10 and log that the UPDATE sector is protected."""
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        assert exc_info.value.error_code == 10
        log = "".join(bsw.drain_debug_log(timeout=2.0))
        assert "UPDATE" in log or "protected" in log.lower()


# ---------------------------------------------------------------------------
# TestUpdateStateAfterSuccess
# ---------------------------------------------------------------------------

class TestUpdateStateAfterSuccess:
    """After a successful upload the system must be in swap-ready state.

    setupSystemForImageSwap() is called before the reset:
      - COMM word = 123 (COMM_STATUS_SWAP)
      - BOOT (sector 5) and COUNTER (sector 9) write-protection must be lifted
    """

    def test_system_state_after_successful_upload(self, nominal_state, bsw, config, image_factory):
        """After upload: COMM=SWAP, BOOT+COUNTER unlocked, UPDATE slot has correct version."""
        import time
        update_img = image_factory.build(version=2)
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        import time; time.sleep(0.5)  # allow BSW to prepare for upload
        bsw.upload_image(update_img, start_sequence=1)
        time.sleep(2.5)  # allow OB_Launch reset from setupSystemForImageSwap

        assert board.get_comm_status() == board.COMM_STATUS_SWAP
        assert not board.is_write_protected(board.OB_WRP_BOOT),    "BOOT sector must be unlocked after upload"
        assert not board.is_write_protected(board.OB_WRP_COUNTER), "COUNTER sector must be unlocked after upload"
        hdr = _read_header_from_slot(board.UPDATE_FLASH_ADDRESS)
        assert hdr["version"] == 2
