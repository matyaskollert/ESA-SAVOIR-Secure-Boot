"""
test_security.py – Security-focused E2E tests for the BSW.

Tests cover:
  - Rollback prevention (counter enforcement)
  - Signature tampering detection
  - Flash write-protection enforcement
  - CRC-corruption detection post-upload
"""

import struct
import pytest

from helpers import board, serial_comm
from helpers.image_factory import ImageFactory


# ---------------------------------------------------------------------------
# TestRollbackPrevention
# ---------------------------------------------------------------------------

class TestRollbackPrevention:
    """The rollback counter must prevent downgrades beyond the allowed window."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_flash, image_factory):
        """Counter = 10, window = 1 → floor = 9.  Upload version 8 → should fail."""
        boot_img = image_factory.build(version=10)
        board.flash_image(board.BOOT_FLASH_ADDRESS, boot_img)
        board.set_rollback_counter(10)

    def test_version_below_floor_rejected_with_nack9(self, bsw, config, image_factory):
        old_img = image_factory.build(version=8)
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        # START
        bsw.send_start_upload(len(old_img), sequence=1)
        bsw.wait_for_ack(expected_sequence=1)
        # First DATA chunk – BSW reads version here
        bsw.send_data_chunk(old_img[:256], sequence=2)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=2)
        assert exc_info.value.error_code == 9

    def test_counter_unchanged_after_rejection(self, bsw, config, image_factory):
        """Counter must not be modified if the upload is rejected."""
        old_img = image_factory.build(version=8)
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.send_start_upload(len(old_img), sequence=1)
        bsw.wait_for_ack(expected_sequence=1)
        bsw.send_data_chunk(old_img[:256], sequence=2)
        try:
            bsw.wait_for_ack(expected_sequence=2)
        except serial_comm.NackReceived:
            pass

        assert board.get_rollback_counter() == 10  # unchanged

    def test_version_at_floor_is_accepted(self, bsw, config, image_factory):
        """Version = floor (9) must be accepted without NACK."""
        floor_img = image_factory.build(version=9)
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(floor_img, start_sequence=1)  # must not raise


# ---------------------------------------------------------------------------
# TestSignatureTampering
# ---------------------------------------------------------------------------

class TestSignatureTampering:
    """BSW must reject images with a tampered digital signature."""

    @pytest.fixture(autouse=True)
    def setup_tampered_update(self, nominal_state, image_factory):
        """Write an image whose first signature byte is flipped to the UPDATE slot
        (without re-signing; the CRC is still valid so the CRC check passes but
        the signature check fails)."""
        good_img   = image_factory.build(version=2)
        bad_sig    = ImageFactory.corrupt_signature(good_img)
        # Recompute CRC so the image survives the CRC check and reaches sig verify
        import binascii
        crc_input  = bad_sig[4:]                          # everything after the CRC field
        new_crc    = binascii.crc32(crc_input) & 0xFFFFFFFF
        bad_img    = struct.pack("<I", new_crc) + bad_sig[4:]
        board.flash_image(board.UPDATE_FLASH_ADDRESS, bad_img)

    def test_signature_failure_during_imageLoad(self, bsw, config):
        """Sending '4' (check versions) calls imageLoad which verifies the sig."""
        board.reset_board(delay=1.0)
        bsw.send_command('4', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        log = "".join(bsw.drain_debug_log(timeout=5.0))
        assert "Digital signature validation failed" in log or "invalid" in log.lower()


# ---------------------------------------------------------------------------
# TestFlashWriteProtection
# ---------------------------------------------------------------------------

class TestFlashWriteProtection:
    """Verify the BSW enforces WRP sector checks before modifying flash."""

    def test_nominal_boot_rejected_when_unprotected(self, nominal_state, bsw, config):
        """Boot is rejected (error 11) when BOOT sector is not write-protected."""
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT,
        )
        import time; time.sleep(1.5)

        try:
            board.reset_board(delay=1.0)
            bsw.send_command('1', sequence=0)
            with pytest.raises(serial_comm.NackReceived) as exc_info:
                bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
            assert exc_info.value.error_code == 11
        finally:
            # Always restore WRP so subsequent tests are not affected
            board.set_write_protection(protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER)
            time.sleep(1.5)


# ---------------------------------------------------------------------------
# TestCrcCorruption
# ---------------------------------------------------------------------------

class TestCrcCorruption:
    """CRC mismatches in both FLASH and RAM must be detected and reported."""

    def test_boot_crc_failure_stops_boot(self, clean_flash, bsw, config, image_factory):
        """A corrupted CRC in the BOOT slot must prevent booting (NACK or no ACK)."""
        good_img = image_factory.build(version=1)
        bad_img  = ImageFactory.corrupt_crc(good_img)
        board.flash_image(board.BOOT_FLASH_ADDRESS, bad_img)

        board.reset_board(delay=1.0)
        bsw.send_command('1', sequence=0)
        with pytest.raises((serial_comm.NackReceived, TimeoutError)):
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)

    def test_boot_crc_failure_logged(self, clean_flash, bsw, config, image_factory):
        """The BSW must log a CRC mismatch message."""
        good_img = image_factory.build(version=1)
        bad_img  = ImageFactory.corrupt_crc(good_img)
        board.flash_image(board.BOOT_FLASH_ADDRESS, bad_img)

        board.reset_board(delay=1.0)
        bsw.send_command('1', sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        except (serial_comm.NackReceived, TimeoutError):
            pass
        log = "".join(bsw.drain_debug_log(timeout=2.0))
        assert "CRC Mismatch" in log
