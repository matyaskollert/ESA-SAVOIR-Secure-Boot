"""
test_swap.py – E2E tests for the BSW image swap path (command '3').

The swap rotates:   SWAP ← BOOT;  BOOT ← UPDATE;  UPDATE ← SWAP

After a successful swap:
  - The BOOT slot contains what was previously in UPDATE.
  - The SWAP slot contains what was previously in BOOT.
  - The rollback counter is updated to the new BOOT version if it is higher.
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

    def test_swap_performs_correctly(self, bsw, clean_flash, image_factory, config):
        """ACK received; primary_slot flipped to SLOT_B, counter=2, sectors re-protected."""
        slot_a_img = image_factory.build(version=1)
        slot_b_img = image_factory.build(version=2)
        board.flash_image(board.SLOT_A_FLASH_ADDRESS, slot_a_img)
        board.flash_image(board.SLOT_B_FLASH_ADDRESS, slot_b_img)
        board.set_rollback_counter(1)
        board.set_primary_flag(board.PROTECTED_BSW_STATE_PRIMARY_SLOT_A)

        # Replicate setupSystemForImageSwap(): COMM=0xCC, unlock SLOT_A+PROTECTED_BSW_STATE
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_SLOT_A | board.OB_WRP_PROTECTED_BSW_STATE,
        )
        board.reset_board()
        bsw.send_command("3", sequence=0)
        ack = bsw.wait_for_ack(expected_sequence=0)
        assert ack is not None
        bsw.drain_debug_log(timeout=5.0)  # let the swap finish

        # Flash contents must be UNCHANGED – swap is flag-based, no data movement.
        assert (
            board.flash_read(board.SLOT_A_FLASH_ADDRESS, len(slot_a_img)) == slot_a_img
        ), "SLOT_A flash contents must be unchanged after flag-based swap"
        assert (
            board.flash_read(board.SLOT_B_FLASH_ADDRESS, len(slot_b_img)) == slot_b_img
        ), "SLOT_B flash contents must be unchanged after flag-based swap"
        # Primary slot flag must now point to SLOT_B.
        assert (
            board.get_primary_flag() == board.PROTECTED_BSW_STATE_PRIMARY_SLOT_B
        ), "primary_slot flag must be SLOT_B after swap"
        # Rollback counter must advance to the new primary (SLOT_B) version.
        assert (
            board.get_rollback_counter() == 2
        ), "Rollback counter must be updated to new primary version after swap"
        # SLOT_B (new primary) and PROTECTED_BSW_STATE must be re-protected.
        assert board.is_write_protected(
            board.OB_WRP_SLOT_B
        ), "New primary slot (SLOT_B) must be write-protected after swap"
        assert board.is_write_protected(
            board.OB_WRP_PROTECTED_BSW_STATE
        ), "PROTECTED_BSW_STATE sector must be re-protected after swap"
        # SLOT_A (now secondary) must be unprotected.
        assert not board.is_write_protected(
            board.OB_WRP_SLOT_A
        ), "Old primary (SLOT_A) must be unprotected after swap"


class TestSwapBootSectorStillProtected:
    """BSW must refuse swap when COMM=0xCC but primary slot (SLOT_A) is still write-protected."""

    @pytest.fixture(autouse=True)
    def setup_boot_protected(self, clean_flash, image_factory):
        """Flash SLOT_A=v1/SLOT_B=v2, set COMM=SWAP, unprotect only PROTECTED_BSW_STATE."""
        slot_a_img = image_factory.build(version=1)
        slot_b_img = image_factory.build(version=2)
        board.flash_image(board.SLOT_A_FLASH_ADDRESS, slot_a_img)
        board.flash_image(board.SLOT_B_FLASH_ADDRESS, slot_b_img)
        board.set_rollback_counter(1)
        board.set_primary_flag(board.PROTECTED_BSW_STATE_PRIMARY_SLOT_A)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=board.OB_WRP_SLOT_A,
            unprotect_mask=board.OB_WRP_PROTECTED_BSW_STATE,
        )
        yield
        board.set_write_protection(
            protect_mask=board.OB_WRP_SLOT_A | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=board.OB_WRP_SLOT_B,
        )

    def test_nack_when_boot_sector_still_protected(self, bsw, config):
        """COMM=SWAP but BOOT sector is still write-protected → NACK 12."""
        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 12


class TestSwapCounterSectorStillProtected:
    """BSW must refuse swap when COMM=0xCC but PROTECTED_BSW_STATE sector is still write-protected."""

    @pytest.fixture(autouse=True)
    def setup_counter_protected(self, clean_flash, image_factory):
        """Flash SLOT_A=v1/SLOT_B=v2, set COMM=SWAP, unprotect only SLOT_A."""
        slot_a_img = image_factory.build(version=1)
        slot_b_img = image_factory.build(version=2)
        board.flash_image(board.SLOT_A_FLASH_ADDRESS, slot_a_img)
        board.flash_image(board.SLOT_B_FLASH_ADDRESS, slot_b_img)
        board.set_rollback_counter(1)
        board.set_primary_flag(board.PROTECTED_BSW_STATE_PRIMARY_SLOT_A)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=board.OB_WRP_SLOT_A,
        )
        yield
        board.set_write_protection(
            protect_mask=board.OB_WRP_SLOT_A | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=board.OB_WRP_SLOT_B,
        )

    def test_nack_when_counter_sector_still_protected(self, bsw, config):
        """COMM=SWAP but COUNTER sector is still write-protected → NACK 12."""
        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 12


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

    def test_nack_when_update_slot_empty(self, swap_ready_state, bsw, config):
        """UPDATE slot erased → imageGetHeader fails → NACK (via checkUpdateVersion)."""
        board.flash_erase_slot(board.SLOT_B_FLASH_ADDRESS)

        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)

    def test_nack_when_update_has_bad_magic(
        self, swap_ready_state, bsw, config, image_factory
    ):
        """UPDATE slot has wrong magic → imageGetHeader returns NULL → NACK."""
        good_img = image_factory.build(version=2)
        bad_img = ImageFactory.corrupt_magic(good_img)
        board.flash_image(board.SLOT_B_FLASH_ADDRESS, bad_img)

        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)

    def test_nack_when_update_has_corrupt_crc(
        self, swap_ready_state, bsw, config, image_factory
    ):
        """UPDATE slot has corrupted CRC → imageValidate fails → NACK."""
        good_img = image_factory.build(version=2)
        bad_img = ImageFactory.corrupt_crc(good_img)
        board.flash_image(board.SLOT_B_FLASH_ADDRESS, bad_img)

        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)

    def test_nack_when_update_has_invalid_signature(
        self, swap_ready_state, bsw, config, image_factory
    ):
        """UPDATE slot CRC is valid but signature is tampered → imageLoad fails → NACK."""
        good_img = image_factory.build(version=2)
        bad_sig = ImageFactory.corrupt_signature(good_img)
        new_crc = binascii.crc32(bad_sig[4:]) & 0xFFFFFFFF
        bad_img = struct.pack("<I", new_crc) + bad_sig[4:]
        board.flash_image(board.SLOT_B_FLASH_ADDRESS, bad_img)

        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived):
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)


class TestSwapVersionRejectionRecovery:
    """After checkUpdateVersion() rejects with NACK 9, the BSW must restore nominal state.

    setupSystemForNominal() is called: COMM ← 0xAA, BOOT and COUNTER re-protected.
    """

    @pytest.fixture(autouse=True)
    def setup_rollback_scenario(self, clean_flash, image_factory):
        """Counter = 5, SLOT_A = v5 (primary), SLOT_B = v3 (below floor=4).  System in SWAP state."""
        slot_a_img = image_factory.build(version=5)
        slot_b_img = image_factory.build(version=3)  # below floor
        board.flash_image(board.SLOT_A_FLASH_ADDRESS, slot_a_img)
        board.flash_image(board.SLOT_B_FLASH_ADDRESS, slot_b_img)
        board.set_rollback_counter(5)
        board.set_primary_flag(board.PROTECTED_BSW_STATE_PRIMARY_SLOT_A)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_SLOT_A | board.OB_WRP_PROTECTED_BSW_STATE,
        )

    def test_nack_9_on_version_below_floor(self, bsw, config):
        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 9


class TestSwapRollbackCounterEdges:
    """Rollback counter update edge cases in updateRollbackCounter()."""

    def test_counter_not_incremented_when_already_current(
        self, swap_ready_state, bsw, config
    ):
        """If the counter already equals the new BOOT version, it must stay unchanged."""
        # swap_ready_state: BOOT=v1, UPDATE=v2, counter=1.
        # After swap: new BOOT=v2, counter should become 2.
        # Pre-set counter = 2 so the new BOOT version == counter.
        board.set_rollback_counter(2)

        board.reset_board()
        bsw.send_command("3", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.drain_debug_log(timeout=2.0)
        time.sleep(1.0)

        # Counter was already 2 (== new BOOT version 2); must stay 2.
        assert board.get_rollback_counter() == 2

    def test_counter_updated_when_new_boot_is_higher(
        self, swap_ready_state, bsw, config
    ):
        """Counter must advance to the new BOOT version when it is higher."""
        # swap_ready_state already has counter=1, BOOT=v1, UPDATE=v2.
        board.reset_board()
        bsw.send_command("3", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.drain_debug_log(timeout=5.0)
        time.sleep(1.0)

        assert board.get_rollback_counter() == 2


class TestSwapRollbackEnforcement:
    """Rollback counter must prevent downgrade at the *swap* stage.

    checkUpdateVersion() is called during command '3'.  The UPDATE image must
    pass CRC + signature before its version is compared against the floor.
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_flash, image_factory):
        """Counter = 10, window = 1 → floor = 9.
        SLOT_A = v10 (primary), SLOT_B = v8 (below floor).  System in SWAP state.
        """
        slot_a_img = image_factory.build(version=10)
        slot_b_img = image_factory.build(version=8)
        board.flash_image(board.SLOT_A_FLASH_ADDRESS, slot_a_img)
        board.flash_image(board.SLOT_B_FLASH_ADDRESS, slot_b_img)
        board.set_rollback_counter(10)
        board.set_primary_flag(board.PROTECTED_BSW_STATE_PRIMARY_SLOT_A)
        board.set_comm_status(board.COMM_STATUS_SWAP)
        board.set_write_protection(
            protect_mask=0,
            unprotect_mask=board.OB_WRP_SLOT_A | board.OB_WRP_PROTECTED_BSW_STATE,
        )

    def test_nack9_and_state_unchanged_after_rejection(self, bsw, config):
        """Version 8 < floor 9 → NACK 9; BOOT slot and counter must be unchanged."""
        board.reset_board()
        bsw.send_command("3", sequence=0)
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        assert exc_info.value.error_code == 9
        time.sleep(1.0)

        raw = board.flash_read(board.SLOT_A_FLASH_ADDRESS, 8)
        _crc, _magic, version = struct.unpack("<IHH", raw)
        assert (
            version == 10
        ), "SLOT_A slot version must be unchanged after rollback rejection"
        assert (
            board.get_rollback_counter() == 10
        ), "Counter must be unchanged after rollback rejection"
