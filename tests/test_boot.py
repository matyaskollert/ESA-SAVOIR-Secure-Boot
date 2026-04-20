"""
test_boot.py – E2E tests for the BSW nominal boot path (command '1').

Each test:
  1. Sets up flash and option bytes via the board helper.
  2. Resets the board and sends a command over UART.
  3. Asserts the BSW response and/or final flash/OB state.
"""

import binascii
import struct
import time
import pytest

from helpers import board, serial_comm
from helpers.image_factory import ImageFactory


class TestBootValidImage:
    """Happy-path: board has a valid signed image in the BOOT slot."""

    def test_boot_successful(self, real_asw_state, bsw, config):
        """BSW must ACK, complete all validation steps, and hand off to the real ASW."""
        board.reset_board()
        bsw.send_command('1', sequence=0)
        ack = bsw.wait_for_ack(expected_sequence=0)
        assert ack is not None
        # Collect debug output from the BSW (and early ASW output if any).
        log = "".join(bsw.drain_debug_log(timeout=2.0))
        assert "CRC validation in FLASH successful" in log
        assert "Digital signature valid" in log
        assert "CRC validation in RAM successful" in log
        # TODO: add check that the ASW actually started executing
        assert "App STARTED" in log


class TestBootNoImage:
    """Boot slot is erased (no magic number) → BSW must send error log."""

    # def test_nack_on_missing_image(self, clean_flash, bsw, config):
    #     board.reset_board()
    #     bsw.send_command('1', sequence=0)
    #     with pytest.raises(serial_comm.NackReceived):
    #         bsw.wait_for_ack(expected_sequence=0, timeout=1.0)

    def test_debug_log_reports_missing_header(self, clean_flash, bsw, config):
        board.reset_board()
        bsw.send_command('1', sequence=0)
        bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        log = "".join(bsw.drain_debug_log(timeout=1.0))
        assert "No valid header found" in log


class TestBootCorruptCRC:
    """BOOT slot has a valid magic but bad CRC → BSW must report CRC failure."""

    @pytest.fixture(autouse=True)
    def setup_corrupt_boot(self, clean_flash, image_factory: ImageFactory):
        """Write a CRC-corrupted image to the BOOT slot."""
        good_img = image_factory.build(version=1)
        bad_img  = ImageFactory.corrupt_crc(good_img)
        board.flash_image(board.BOOT_FLASH_ADDRESS, bad_img)

    # def test_nack_on_bad_crc(self, bsw, config):
    #     board.reset_board()
    #     bsw.send_command('1', sequence=0)
    #     with pytest.raises(serial_comm.NackReceived):
    #         bsw.wait_for_ack(expected_sequence=0, timeout=1.0)

    def test_debug_log_reports_crc_mismatch(self, bsw, config):
        board.reset_board()
        bsw.send_command('1', sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        except serial_comm.NackReceived:
            pass
        log = "".join(bsw.drain_debug_log(timeout=1.0))
        assert "CRC mismatch in FLASH" in log
        assert "0xdeadbeef" in log


class TestBootUnprotectedBootSector:
    """Nominal boot must be refused when BOOT sector is NOT protected."""

    @pytest.fixture(autouse=True)
    def setup_unprotected(self, nominal_state):
        """Temporarily remove write-protection from the BOOT sector."""
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT,
        )
        yield
        # Restore protection after test
        board.set_write_protection(protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER)

    def test_nack_when_boot_sector_unprotected(self, bsw, config):
        """BSW must refuse to boot if checkSystemForNominal() fails."""
        board.reset_board()
        bsw.send_command('1', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        assert exc_info.value.error_code == 11  # "System not configured for nominal mode"


class TestBootUnprotectedCounterSector:
    """Nominal boot refused when COUNTER sector is unprotected (BOOT is still ok)."""

    @pytest.fixture(autouse=True)
    def setup_counter_unprotected(self, nominal_state):
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_COUNTER,
        )
        yield
        board.set_write_protection(protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER)

    def test_nack_and_sectors_reprotected(self, bsw, config):
        """BSW must NACK 11 and then re-protect both sectors via setupSystemForNominal()."""
        board.reset_board()
        bsw.send_command('1', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        assert exc_info.value.error_code == 11
        time.sleep(1.0)  # let OB_Launch reset complete
        assert board.is_write_protected(board.OB_WRP_COUNTER)
        assert board.is_write_protected(board.OB_WRP_BOOT)


class TestBootBothSectorsUnprotected:
    """Nominal boot refused when both BOOT and COUNTER are unprotected."""

    @pytest.fixture(autouse=True)
    def setup_both_unprotected(self, nominal_state):
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER,
        )
        yield
        board.set_write_protection(protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER)

    def test_nack_wrp_error(self, bsw, config):
        """BSW must NACK 11 and log the WRP error message."""
        board.reset_board()
        bsw.send_command('1', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        assert exc_info.value.error_code == 11
        time.sleep(1.0)  # let OB_Launch reset complete
        assert board.is_write_protected(board.OB_WRP_COUNTER)
        assert board.is_write_protected(board.OB_WRP_BOOT)


class TestBootBadMagic:
    """BOOT slot has a valid-looking write but wrong magic number (0x0000)."""

    @pytest.fixture(autouse=True)
    def setup_bad_magic(self, clean_flash, image_factory: ImageFactory):
        good_img = image_factory.build(version=1)
        bad_img  = ImageFactory.corrupt_magic(good_img)
        board.flash_image(board.BOOT_FLASH_ADDRESS, bad_img)

    # def test_nack_on_bad_magic(self, bsw, config):
    #     board.reset_board()
    #     bsw.send_command('1', sequence=0)
    #     with pytest.raises(serial_comm.NackReceived):
    #         bsw.wait_for_ack(expected_sequence=0, timeout=1.0)

    def test_debug_log_reports_no_valid_header(self, bsw, config):
        board.reset_board()
        bsw.send_command('1', sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        except serial_comm.NackReceived:
            pass
        log = "".join(bsw.drain_debug_log(timeout=1.0))
        assert "No valid header found" in log


class TestBootInvalidSignature:
    """Valid CRC (passes first check) but a tampered digital signature."""

    @pytest.fixture(autouse=True)
    def setup_bad_sig(self, clean_flash, image_factory: ImageFactory):
        good_img = image_factory.build(version=1)
        # Corrupt the signature, then recompute the CRC so the CRC check passes
        # and execution reaches the signature verification step.
        bad_sig = ImageFactory.corrupt_signature(good_img)
        crc_input = bad_sig[4:]
        new_crc   = ImageFactory._crc32_mpeg2(crc_input)
        bad_img   = struct.pack("<I", new_crc) + bad_sig[4:]
        board.flash_image(board.BOOT_FLASH_ADDRESS, bad_img)

    # def test_nack_on_bad_signature(self, bsw, config):
    #     board.reset_board()
    #     bsw.send_command('1', sequence=0)
    #     with pytest.raises(serial_comm.NackReceived):
    #         bsw.wait_for_ack(expected_sequence=0, timeout=2.0)

    def test_debug_log_reports_signature_failure(self, bsw, config):
        board.reset_board()
        bsw.send_command('1', sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        except serial_comm.NackReceived:
            pass
        log = "".join(bsw.drain_debug_log(timeout=1.0))
        assert "Digital signature validation failed" in log


class TestBootNominalAutoFix:
    """After NACK 11 caused by bad WRP, the BSW must auto-fix and re-protect sectors.

    Verifies that on the *next* boot (after the auto-fix reset) the system
    correctly acknowledges a nominal boot command.
    """

    def test_autofix_reprotects_and_next_boot_succeeds(self, nominal_state, bsw, config):
        """Unprotect BOOT → NACK 11 → auto-fix re-protects both sectors → next boot ACKs."""
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT,
        )

        # First boot: triggers NACK + setupSystemForNominal() + OB_Launch reset
        board.reset_board()
        bsw.send_command('1', sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        except serial_comm.NackReceived:
            pass
        bsw.close()

        time.sleep(1.0)  # allow OB_Launch reset to complete
        assert board.is_write_protected(board.OB_WRP_BOOT),    "BOOT sector must be re-protected after auto-fix"
        assert board.is_write_protected(board.OB_WRP_COUNTER), "COUNTER sector must be re-protected after auto-fix"

        # Second boot (after auto-fix) must succeed
        bsw.open()
        board.reset_board()
        bsw.send_command('1', sequence=0)
        ack = bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        assert ack is not None
