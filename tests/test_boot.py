"""
test_boot.py - E2E tests for the BSW nominal boot path (command '1').

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
    """Happy-path: board has a valid signed image in the MAIN slot."""

    def test_boot_successful(self, real_asw_state, slot_config, bsw, config):
        """BSW must ACK, complete all validation steps, and hand off to the real ASW."""
        board.reset_board()
        bsw.send_command("1", sequence=0)
        ack = bsw.wait_for_ack(expected_sequence=0)
        assert ack is not None
        # Collect debug output from the BSW (and early ASW output if any).
        log = "".join(bsw.drain_debug_log(timeout=3.0))
        assert "CRC validation in FLASH successful" in log
        assert "Digital signature valid" in log
        assert "CRC validation in RAM successful" in log

        # check that the ASW actually started executing
        assert "App STARTED" in log

        # Verify the BSW report persisted to flash
        report = board.get_latest_report()
        assert (
            report is not None
        ), "A NOMINAL report must be written after a successful boot"
        assert report["type"] == board.BSW_REPORT_TYPE_NOMINAL
        assert report["outcome"] == 0
        assert report["step_flags"] == (
            board.BSW_NOMINAL_FLAG_SYSTEM_OK
            | board.BSW_NOMINAL_FLAG_STATUS_SET
            | board.BSW_NOMINAL_FLAG_CRC_OK
            | board.BSW_NOMINAL_FLAG_SIG_OK
            | board.BSW_NOMINAL_FLAG_RAM_CRC_OK
        )
        assert report["primary_slot"] == slot_config.primary_slot_enum


class TestBootNoImage:
    """MAIN slot is erased (no magic number) → BSW must send error log."""

    def test_debug_log_reports_missing_header(self, clean_flash, slot_config, bsw, config):
        board.reset_board()
        bsw.send_command("1", sequence=0)
        bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        log = "".join(bsw.drain_debug_log(timeout=2.0))
        assert "No valid header found" in log
        # BSW must write a NOMINAL report recording the CRC failure
        report = board.get_latest_report()
        assert report is not None, "A NOMINAL report must be written when boot fails"
        assert report["type"] == board.BSW_REPORT_TYPE_NOMINAL
        assert report["outcome"] == 2
        assert report["step_flags"] == (
            board.BSW_NOMINAL_FLAG_SYSTEM_OK | board.BSW_NOMINAL_FLAG_STATUS_SET
        )
        assert report["primary_slot"] == slot_config.primary_slot_enum


class TestBootCorruptCRC:
    """MAIN slot has a valid magic but bad CRC → BSW must report CRC failure."""

    @pytest.fixture(autouse=True)
    def setup_corrupt_boot(self, clean_flash, slot_config, image_factory: ImageFactory):
        """Write a CRC-corrupted image to the MAIN slot."""
        good_img = image_factory.build(version=1)
        bad_img = ImageFactory.corrupt_crc(good_img)
        board.flash_image(slot_config.primary_address, bad_img)

    def test_debug_log_reports_crc_mismatch(self, slot_config, bsw, config):
        board.reset_board()
        bsw.send_command("1", sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        except serial_comm.NackReceived:
            pass
        log = "".join(bsw.drain_debug_log(timeout=2.0))
        assert "CRC mismatch in FLASH" in log
        assert "0xdeadbeef" in log
        # BSW must write a NOMINAL report with CRC failure
        report = board.get_latest_report()
        assert report is not None, "A NOMINAL report must be written when CRC fails"
        assert report["type"] == board.BSW_REPORT_TYPE_NOMINAL
        assert report["outcome"] == 2
        assert report["step_flags"] == (
            board.BSW_NOMINAL_FLAG_SYSTEM_OK | board.BSW_NOMINAL_FLAG_STATUS_SET
        )
        assert report["primary_slot"] == slot_config.primary_slot_enum


class TestBootUnprotectedMainSector:
    """Nominal boot must be refused when MAIN sector is NOT protected."""

    @pytest.fixture(autouse=True)
    def setup_unprotected(self, nominal_state, slot_config):
        """Temporarily remove write-protection from the MAIN sector."""
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=slot_config.primary_ob_mask,
        )
        yield
        # Restore protection after test
        board.set_write_protection(
            protect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=slot_config.secondary_ob_mask,
        )

    def test_nack_when_boot_sector_unprotected(self, bsw, config):
        """BSW must refuse to boot if checkSystemForNominal() fails."""
        board.reset_board()
        bsw.send_command("1", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        assert (
            exc_info.value.error_code == 11
        )  # "System not configured for nominal mode"

        # BSW writes a NOMINAL report (outcome=5) before calling setupSystemForNominal()
        report = board.get_latest_report()
        assert (
            report is not None
        ), "A NOMINAL report must be written on system check failure"
        assert report["type"] == board.BSW_REPORT_TYPE_NOMINAL
        assert report["outcome"] == 5
        assert report["step_flags"] == 0


class TestBootUnprotectedBSWStateSector:
    """Nominal boot refused when PROTECTED_BSW_STATE sector is unprotected (MAIN is still ok)."""

    @pytest.fixture(autouse=True)
    def setup_bsw_state_unprotected(self, nominal_state, slot_config):
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
        """BSW must NACK 11 and then re-protect both sectors via setupSystemForNominal()."""
        board.reset_board()
        bsw.send_command("1", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        assert exc_info.value.error_code == 11
        time.sleep(1.0)  # let OB_Launch reset complete
        assert board.is_write_protected(board.OB_WRP_PROTECTED_BSW_STATE)
        assert board.is_write_protected(slot_config.primary_ob_mask)

        # BSW writes a NOMINAL report (outcome=5) before calling setupSystemForNominal()
        report = board.get_latest_report()
        assert (
            report is not None
        ), "A NOMINAL report must be written on system check failure"
        assert report["type"] == board.BSW_REPORT_TYPE_NOMINAL
        assert report["outcome"] == 5
        assert report["step_flags"] == 0


class TestBootBothSectorsUnprotected:
    """Nominal boot refused when both MAIN and PROTECTED_BSW_STATE are unprotected."""

    @pytest.fixture(autouse=True)
    def setup_both_unprotected(self, nominal_state, slot_config):
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
        )
        yield
        board.set_write_protection(
            protect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=slot_config.secondary_ob_mask,
        )

    def test_nack_wrp_error(self, slot_config, bsw, config):
        """BSW must NACK 11 and log the WRP error message."""
        board.reset_board()
        bsw.send_command("1", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        assert exc_info.value.error_code == 11
        time.sleep(1.0)  # let OB_Launch reset complete
        assert board.is_write_protected(board.OB_WRP_PROTECTED_BSW_STATE)
        assert board.is_write_protected(slot_config.primary_ob_mask)

        # BSW writes a NOMINAL report (outcome=5) before calling setupSystemForNominal()
        report = board.get_latest_report()
        assert (
            report is not None
        ), "A NOMINAL report must be written on system check failure"
        assert report["type"] == board.BSW_REPORT_TYPE_NOMINAL
        assert report["outcome"] == 5
        assert report["step_flags"] == 0


class TestBootBadMagic:
    """MAIN slot has a valid-looking write but wrong magic number (0x0000)."""

    @pytest.fixture(autouse=True)
    def setup_bad_magic(self, clean_flash, slot_config, image_factory: ImageFactory):
        good_img = image_factory.build(version=1)
        bad_img = ImageFactory.corrupt_magic(good_img)
        board.flash_image(slot_config.primary_address, bad_img)

    def test_debug_log_reports_no_valid_header(self, bsw, config):
        board.reset_board()
        bsw.send_command("1", sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        except serial_comm.NackReceived:
            pass
        log = "".join(bsw.drain_debug_log(timeout=2.0))
        assert "No valid header found" in log
        # Bad magic → imageGetHeader returns NULL → imageValidate fails with outcome=2
        report = board.get_latest_report()
        assert report is not None
        assert report["type"] == board.BSW_REPORT_TYPE_NOMINAL
        assert report["outcome"] == 2
        assert report["step_flags"] == (
            board.BSW_NOMINAL_FLAG_SYSTEM_OK | board.BSW_NOMINAL_FLAG_STATUS_SET
        )


class TestBootInvalidSignature:
    """Valid CRC (passes first check) but a tampered digital signature."""

    @pytest.fixture(autouse=True)
    def setup_bad_sig(self, clean_flash, slot_config, image_factory: ImageFactory):
        good_img = image_factory.build(version=1)
        # Corrupt the signature, then recompute the CRC so the CRC check passes
        # and execution reaches the signature verification step.
        bad_sig = ImageFactory.corrupt_signature(good_img)
        crc_input = bad_sig[4:]
        new_crc = ImageFactory._crc32_mpeg2(crc_input)
        bad_img = struct.pack("<I", new_crc) + bad_sig[4:]
        board.flash_image(slot_config.primary_address, bad_img)

    def test_debug_log_reports_signature_failure(self, bsw, config):
        board.reset_board()
        bsw.send_command("1", sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        except serial_comm.NackReceived:
            pass
        log = "".join(bsw.drain_debug_log(timeout=2.0))
        assert "Digital signature validation failed" in log
        # CRC passes then signature fails: STATUS_SET and CRC_OK must be set; outcome=3
        report = board.get_latest_report()
        assert report is not None
        assert report["type"] == board.BSW_REPORT_TYPE_NOMINAL
        assert report["outcome"] == 3
        assert report["step_flags"] == (
            board.BSW_NOMINAL_FLAG_SYSTEM_OK
            | board.BSW_NOMINAL_FLAG_STATUS_SET
            | board.BSW_NOMINAL_FLAG_CRC_OK
        )


class TestBootNominalAutoFix:
    """After NACK 11 caused by bad WRP, the BSW must auto-fix and re-protect sectors.

    Verifies that on the *next* boot (after the auto-fix reset) the system
    correctly acknowledges a nominal boot command.
    """

    def test_autofix_reprotects_and_next_boot_succeeds(
        self, nominal_state, slot_config, bsw, config
    ):
        """Unprotect MAIN → NACK 11 → auto-fix re-protects both sectors → next boot ACKs."""
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=slot_config.primary_ob_mask,
        )

        # First boot: triggers NACK + setupSystemForNominal() + OB_Launch reset
        board.reset_board()
        bsw.send_command("1", sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        except serial_comm.NackReceived:
            pass
        bsw.close()

        time.sleep(1.0)  # allow OB_Launch reset to complete
        assert board.is_write_protected(
            slot_config.primary_ob_mask
        ), "Primary slot sector must be re-protected after auto-fix"
        assert board.is_write_protected(
            board.OB_WRP_PROTECTED_BSW_STATE
        ), "PROTECTED_BSW_STATE sector must be re-protected after auto-fix"

        # Second boot (after auto-fix) must succeed
        bsw.open()
        board.reset_board()
        bsw.send_command("1", sequence=0)
        ack = bsw.wait_for_ack(expected_sequence=0, timeout=1.0)
        assert ack is not None
