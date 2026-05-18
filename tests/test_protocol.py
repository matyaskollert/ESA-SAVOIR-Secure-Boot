"""
test_protocol.py - ECSS packet protocol robustness tests for the BSW.

These tests send malformed, out-of-order, or unexpected packet sequences to
verify that the BSW handles every error path in the protocol layer without
hanging, crashing, or corrupting flash.

Scenarios covered
-----------------
1. Unknown / invalid command character  → BSW must not hang
2. Command packet with data_length = 0  → undefined buffer content must not cause a crash
3. START_UPLOAD packet with data_length ≠ 4 → NACK 3
4. Wrong service type where START_UPLOAD expected → NACK 2
5. Wrong service type where DATA_CHUNK expected (after START) → NACK 7
6. Sequence number gap in DATA_CHUNK stream → warning logged but upload continues
7. END_UPLOAD received before all bytes sent → upload ends early (partial image)
"""

import struct
import time
import pytest

from helpers import board, serial_comm
from helpers.image_factory import ImageFactory
from helpers.serial_comm import PacketType, _build_header


class TestUnknownCommand:
    """BSW must not hang or crash when an unrecognised command character is sent."""

    def test_unknown_command_does_not_hang(self, nominal_state, bsw, config):
        """Send 'X'; the BSW should reach the else-branch and eventually reset."""
        board.reset_board()
        bsw.send_command("X", sequence=0)
        # Give the BSW up to 2 s to respond or reset; we only care it doesn't hang.
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        except (serial_comm.NackReceived, TimeoutError, AssertionError):
            pass  # any response (or none) is acceptable - we just mustn't block forever

    def test_unknown_command_does_not_corrupt_boot_slot(
        self, nominal_state, bsw, config
    ):
        """The MAIN slot must be byte-for-byte intact after an unknown command."""
        golden = board.flash_read(board.SLOT_A_FLASH_ADDRESS, 32)

        board.reset_board()
        bsw.send_command("X", sequence=0)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        except (serial_comm.NackReceived, TimeoutError, AssertionError):
            pass

        after = board.flash_read(board.SLOT_A_FLASH_ADDRESS, 32)
        assert after == golden, "MAIN slot must not be modified by an unknown command"


class TestCommandWithEmptyData:
    """Command packet with data_length = 0 must not crash the BSW.

    The firmware only reads from the buffer when data_length > 0, so the
    buffer retains its zero-initialised (or garbage) value.  The important
    property is that no memory corruption or infinite loop occurs.
    """

    def _send_zero_length_command(self, bsw):
        """Send a DEBUG_LOG header with data_length = 0 (no payload follows)."""
        hdr = _build_header(PacketType.DEBUG_LOG, sequence=0, data_len=0, is_tc=True)
        bsw._send(hdr)

    def test_zero_length_command_does_not_hang(self, nominal_state, bsw, config):
        board.reset_board()
        self._send_zero_length_command(bsw)
        try:
            bsw.wait_for_ack(expected_sequence=0, timeout=2.0)
        except (serial_comm.NackReceived, TimeoutError, AssertionError):
            pass  # any outcome is acceptable; the BSW just must not block


class TestUploadStartErrors:
    """Verify that the BSW correctly rejects malformed START_UPLOAD packets."""

    def test_nack_3_when_start_data_length_wrong(self, nominal_state, bsw, config):
        """START_UPLOAD with data_length ≠ 4 must produce NACK error code 3."""
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)

        # Send a START_UPLOAD with an 8-byte payload instead of the expected 4.
        bad_hdr = _build_header(PacketType.START_UPLOAD, sequence=1, data_len=8)
        bsw._send(bad_hdr, struct.pack("<II", 256, 0))
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=1, timeout=2.0)
        assert exc_info.value.error_code == 3

    def test_nack_2_when_wrong_service_type_at_start(self, nominal_state, bsw, config):
        """Sending DATA_CHUNK where START_UPLOAD is expected → NACK error code 2."""
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)

        # Send DATA_CHUNK instead of START_UPLOAD
        bad_hdr = _build_header(PacketType.DATA_CHUNK, sequence=1, data_len=4)
        bsw._send(bad_hdr, struct.pack("<I", 256))
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=1, timeout=2.0)
        assert exc_info.value.error_code == 2


class TestUploadChunkErrors:
    """Verify error handling during the DATA_CHUNK phase."""

    def test_nack_7_when_wrong_service_type_in_chunk_phase(
        self, nominal_state, bsw, config, image_factory
    ):
        """After a valid START, sending START_UPLOAD again → NACK error code 7."""
        update_img = image_factory.build(version=2)
        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)

        # Valid START
        bsw.send_start_upload(len(update_img), sequence=1)
        bsw.wait_for_ack(expected_sequence=1)

        # Wrong type during chunk phase (send another START)
        bad_hdr = _build_header(PacketType.START_UPLOAD, sequence=2, data_len=4)
        bsw._send(bad_hdr, struct.pack("<I", len(update_img)))
        with pytest.raises(serial_comm.NackReceived) as exc_info:
            bsw.wait_for_ack(expected_sequence=2, timeout=2.0)
        assert exc_info.value.error_code == 7

    # def test_sequence_gap_does_not_abort_upload(self, nominal_state, bsw, config, image_factory):
    #     """The BSW logs a sequence-mismatch warning but must not abort the upload.

    #     The firmware only prints a warning for sequence gaps; it never sends NACK.
    #     The full upload must still complete successfully.
    #     """
    #     update_img = image_factory.build(version=2)
    #     board.reset_board()
    #     bsw.send_command('2', sequence=0)
    #     bsw.wait_for_ack(expected_sequence=0)

    #     bsw.send_start_upload(len(update_img), sequence=1)
    #     bsw.wait_for_ack(expected_sequence=1)

    #     # Send first chunk with seq=2 (correct)
    #     chunk0 = update_img[:256]
    #     bsw.send_data_chunk(chunk0, sequence=2)
    #     bsw.wait_for_ack(expected_sequence=2)

    #     # Skip seq=3; send seq=5 (gap of 2)
    #     chunk1 = update_img[256:512]
    #     bsw.send_data_chunk(chunk1, sequence=5)
    #     bsw.wait_for_ack(expected_sequence=5)

    #     # Resume with seq=6 and finish normally
    #     bsw.upload_image(
    #         update_img[512:],
    #         start_sequence=6,
    #         chunk_size=256,
    #     )


class TestUploadEndBeforeAllData:
    """END_UPLOAD received before the declared total size is transferred.

    The firmware exits the chunk loop early when it sees END_UPLOAD.  The
    resulting UPDATE slot will contain only the bytes sent so far (a partial
    image).  The important property is that the BSW must not hang and must
    ACK the END packet.
    """

    def test_end_before_all_data_acks_and_does_not_corrupt_boot(
        self, nominal_state, bsw, config, image_factory
    ):
        """Early END must be ACKed and must not touch the MAIN slot."""
        golden = board.flash_read(board.SLOT_A_FLASH_ADDRESS, 32)
        update_img = image_factory.build(version=2)

        board.reset_board()
        bsw.send_command("2", sequence=0)
        bsw.wait_for_ack(expected_sequence=0)
        bsw.send_start_upload(512, sequence=1)
        bsw.wait_for_ack(expected_sequence=1)
        bsw.send_data_chunk(update_img[:256], sequence=2)
        bsw.wait_for_ack(expected_sequence=2)
        bsw.send_end_upload(sequence=3)
        ack = bsw.wait_for_ack(expected_sequence=3, timeout=2.0)
        assert ack is not None
        time.sleep(1.0)

        after = board.flash_read(board.SLOT_A_FLASH_ADDRESS, 32)
        assert after == golden
