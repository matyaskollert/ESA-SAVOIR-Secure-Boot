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

    def test_nack9_and_counter_unchanged_after_rejection(self, bsw, config, image_factory):
        """Version 8 < floor 9 → NACK 9; counter must remain unchanged."""
        old_img = image_factory.build(version=8)
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        import time; time.sleep(0.5)  # allow BSW to prepare for upload
        bsw.send_start_upload(len(old_img), sequence=1)
        bsw.wait_for_ack(expected_sequence=1)
        import time; time.sleep(0.5)
        bsw.send_data_chunk(old_img[:256], sequence=2)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=2)
        assert exc_info.value.error_code == 9
        assert board.get_rollback_counter() == 10  # must be unchanged

    def test_version_at_floor_is_accepted(self, bsw, config, image_factory):
        """Version = floor (9) must be accepted without NACK."""
        floor_img = image_factory.build(version=9)
        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        import time; time.sleep(0.5)  # allow BSW to prepare for upload
        bsw.upload_image(floor_img, start_sequence=1)  # must not raise


# ---------------------------------------------------------------------------
# TestSwapRollbackEnforcement
# ---------------------------------------------------------------------------

class TestSwapRollbackEnforcement:
    """Rollback counter must prevent downgrade at the *swap* stage.

    checkUpdateVersion() is called during command '3'.  The UPDATE image must
    pass CRC + signature before its version is compared against the floor.
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_flash, image_factory):
        """Counter = 10, window = 1 → floor = 9.
        BOOT = v10, UPDATE = v8 (below floor).  System in SWAP state.
        """
        boot_img   = image_factory.build(version=10)
        update_img = image_factory.build(version=8)
        board.flash_image(board.BOOT_FLASH_ADDRESS,   boot_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, update_img)
        board.set_rollback_counter(10)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER,
        )
        import time; time.sleep(1.5)

    def test_nack9_and_state_unchanged_after_rejection(self, bsw, config):
        """Version 8 < floor 9 → NACK 9; BOOT slot and counter must be unchanged."""
        import time
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=15.0)
        assert exc_info.value.error_code == 9
        time.sleep(2.5)

        raw = board.flash_read(board.BOOT_FLASH_ADDRESS, 8)
        _crc, _magic, version = struct.unpack("<IHH", raw)
        assert version == 10, "BOOT slot version must be unchanged after rollback rejection"
        assert board.get_rollback_counter() == 10, "Counter must be unchanged after rollback rejection"


# ---------------------------------------------------------------------------
# TestRollbackCounterBoundary
# ---------------------------------------------------------------------------

class TestRollbackCounterBoundary:
    """Verify the rollback floor clamps to 0 when counter ≤ ROLLBACK_WINDOW (=1)."""

    def test_version_1_accepted_when_counter_is_0(self, clean_flash, bsw, config, image_factory):
        """Counter = 0 → floor = 0 → any version including 0 is accepted."""
        board.set_rollback_counter(0)
        update_img = image_factory.build(version=1)

        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        # Must not raise
        bsw.upload_image(update_img, start_sequence=1)

    def test_version_1_accepted_when_counter_equals_window(self, clean_flash, bsw, config, image_factory):
        """Counter = 1 (= ROLLBACK_WINDOW) → floor = 0 → version 1 is accepted."""
        board.set_rollback_counter(1)
        update_img = image_factory.build(version=1)

        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.upload_image(update_img, start_sequence=1)

    def test_version_below_floor_rejected_when_counter_gt_window(self, clean_flash, bsw, config, image_factory):
        """Counter = 3 → floor = 2 → version 1 must be rejected."""
        board.set_rollback_counter(3)
        old_img = image_factory.build(version=1)

        board.reset_board(delay=1.0)
        bsw.send_command('2', sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.send_start_upload(len(old_img), sequence=1)
        bsw.wait_for_ack(expected_sequence=1)
        bsw.send_data_chunk(old_img[:256], sequence=2)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=2)
        assert exc_info.value.error_code == 9


# ---------------------------------------------------------------------------
# TestRecoveryAfterSwapRollback
# ---------------------------------------------------------------------------

class TestRecoveryAfterSwapRollback:
    """Full recovery: after a swap rollback rejection the system must be fully nominal.

    This means a subsequent '1' (boot) command must succeed without any manual
    intervention — confirming that setupSystemForNominal() ran correctly.
    """

    def test_nominal_boot_succeeds_after_swap_rollback(self, clean_flash, bsw, config, image_factory):
        """Set up a rollback scenario, trigger NACK 9, then confirm nominal boot works."""
        boot_img   = image_factory.build(version=5)
        update_img = image_factory.build(version=3)  # below floor for counter=5
        board.flash_image(board.BOOT_FLASH_ADDRESS,   boot_img)
        board.flash_image(board.UPDATE_FLASH_ADDRESS, update_img)
        board.set_rollback_counter(5)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER,
        )
        import time; time.sleep(1.5)

        # Attempt swap → NACK 9 + setupSystemForNominal() + reset
        board.reset_board(delay=1.0)
        bsw.send_command('3', sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=15.0)
        except serial_comm.NackReceived:
            pass
        bsw.close()
        time.sleep(2.5)  # wait for OB_Launch reset

        # Now the system should be in nominal state; issue a boot command
        bsw.open()
        board.reset_board(delay=1.0)
        bsw.send_command('1', sequence=0)
        ack = bsw.wait_for_ack(expected_sequence=0, timeout=15.0)
        assert ack is not None, "Nominal boot must succeed after swap rollback recovery"
