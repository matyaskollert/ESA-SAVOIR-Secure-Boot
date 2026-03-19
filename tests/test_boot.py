"""
test_boot.py – E2E tests for the BSW nominal boot path (command '1').

Each test:
  1. Sets up flash and option bytes via the board helper.
  2. Resets the board and sends a command over UART.
  3. Asserts the BSW response and/or final flash/OB state.
"""

import struct
import pytest

from conftest import reset_and_connect
from helpers import board, serial_comm
from helpers.image_factory import ImageFactory


# ---------------------------------------------------------------------------
# test_boot_valid_image
# ---------------------------------------------------------------------------

class TestBootValidImage:
    """Happy-path: board has a valid signed image in the BOOT slot."""

    def test_ack_received(self, nominal_state, bsw, config):
        """BSW must ACK the boot command when BOOT slot is valid and WRP is set."""
        board.reset_board(delay=1.0)
        bsw.send_command('1', sequence=0)
        ack = bsw.wait_for_ack(expected_sequence=0)
        assert ack is not None

    def test_debug_log_reports_crc_ok(self, nominal_state, bsw, config):
        """Debug log should contain CRC success message when booting."""
        board.reset_board(delay=1.0)
        bsw.send_command('1', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        log = "".join(bsw.drain_debug_log(timeout=3.0))
        assert "CRC validation in FLASH successful" in log

    def test_debug_log_reports_signature_ok(self, nominal_state, bsw, config):
        """Digital signature validation must be reported as valid."""
        board.reset_board(delay=1.0)
        bsw.send_command('1', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        log = "".join(bsw.drain_debug_log(timeout=3.0))
        assert "Digital signature valid" in log


# ---------------------------------------------------------------------------
# test_boot_no_image
# ---------------------------------------------------------------------------

class TestBootNoImage:
    """Boot slot is erased (no magic number) → BSW must NACK."""

    def test_nack_on_missing_image(self, clean_flash, bsw, config):
        board.reset_board(delay=1.0)
        bsw.send_command('1', sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)

    def test_debug_log_reports_missing_header(self, clean_flash, bsw, config):
        board.reset_board(delay=1.0)
        bsw.send_command('1', sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        except serial_comm.NackReceived:
            pass
        log = "".join(bsw.drain_debug_log(timeout=2.0))
        assert "No valid header" in log or "ERROR" in log


# ---------------------------------------------------------------------------
# test_boot_corrupt_crc
# ---------------------------------------------------------------------------

class TestBootCorruptCRC:
    """BOOT slot has a valid magic but bad CRC → BSW must report CRC failure."""

    @pytest.fixture(autouse=True)
    def setup_corrupt_boot(self, clean_flash, image_factory: ImageFactory):
        """Write a CRC-corrupted image to the BOOT slot."""
        good_img = image_factory.build(version=1)
        bad_img  = ImageFactory.corrupt_crc(good_img)
        board.flash_image(board.BOOT_FLASH_ADDRESS, bad_img)

    def test_nack_on_bad_crc(self, bsw, config):
        board.reset_board(delay=1.0)
        bsw.send_command('1', sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)

    def test_debug_log_reports_crc_mismatch(self, bsw, config):
        board.reset_board(delay=1.0)
        bsw.send_command('1', sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        except serial_comm.NackReceived:
            pass
        log = "".join(bsw.drain_debug_log(timeout=2.0))
        assert "CRC Mismatch" in log


# ---------------------------------------------------------------------------
# test_boot_unprotected_sectors
# ---------------------------------------------------------------------------

class TestBootUnprotectedSectors:
    """Nominal boot must be refused when BOOT/COUNTER sectors are NOT protected."""

    @pytest.fixture(autouse=True)
    def setup_unprotected(self, nominal_state):
        """Temporarily remove write-protection from the BOOT sector."""
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT,
        )
        import time; time.sleep(1.5)  # wait for OB_Launch reset
        yield
        # Restore protection after test
        board.set_write_protection(protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER)
        import time; time.sleep(1.5)

    def test_nack_when_boot_sector_unprotected(self, bsw, config):
        """BSW must refuse to boot if checkSystemForNominal() fails."""
        board.reset_board(delay=1.0)
        bsw.send_command('1', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=5.0)
        assert exc_info.value.error_code == 11  # "System not configured for nominal mode"
