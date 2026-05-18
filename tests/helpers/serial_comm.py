"""
serial_comm.py \u2014 ECSS serial I/O layer for the BSW E2E test suite.

Mirrors the framing logic in uploader/ecss_packet.py so that tests can speak
the same protocol as the GUI uploader without importing its PySide6 dependency.
All I/O is synchronous; the BSW is single-threaded and processes one command at
a time so blocking reads with a timeout are sufficient.

Public API
----------
  PacketType        \u2014 service-type enum (subset used by tests)
  send_command      \u2014 send a single-byte bootloader command packet
  recv_packet       \u2014 receive and parse one ECSS packet with timeout
  recv_ack          \u2014 receive and assert a PKT_ACK packet
  NackReceived      \u2014 exception raised when a NACK is returned by the BSW
  send_start_upload \u2014 initiate an image upload session
  send_chunk        \u2014 send one DATA_CHUNK packet
  send_end_upload   \u2014 terminate an upload session
"""

import struct
import time
from enum import IntEnum
from typing import Optional

import serial

# ---------------------------------------------------------------------------
# Packet types - must match BSW firmware and uploader/ecss_packet.py
# ---------------------------------------------------------------------------


class PacketType(IntEnum):
    START_UPLOAD = 0x01
    DATA_CHUNK = 0x02
    END_UPLOAD = 0x03
    DEBUG_LOG = 0x04
    ACK = 0x06
    NACK = 0x15


HEADER_SIZE = 7  # bytes
VERSION = 0b001


# ---------------------------------------------------------------------------
# Packet helpers
# ---------------------------------------------------------------------------


def _build_header(
    service_type: int, sequence: int, data_len: int, is_tc: bool = True
) -> bytes:
    vtf = (VERSION << 5) | ((1 if is_tc else 0) << 4)
    hdr_no_crc = struct.pack(">BBHH", vtf, service_type, sequence & 0xFFFF, data_len)
    checksum = 0
    for b in hdr_no_crc:
        checksum ^= b
    return hdr_no_crc + bytes([checksum])


def _parse_header(raw: bytes) -> dict:
    if len(raw) != HEADER_SIZE:
        raise ValueError(f"Header must be {HEADER_SIZE} bytes, got {len(raw)}")
    # print("Raw header bytes:", " ".join(f"0x{b:02X}" for b in raw))
    vtf, svc, seq, dlen, chk = struct.unpack(">BBHHB", raw)
    calc = 0
    for b in raw[:6]:
        # print(f"0x{b:02X}")
        calc ^= b
    if chk != calc:
        print(
            f"Header checksum mismatch: raw={raw.hex()} vtf={vtf:02X} svc={svc:02X} seq={seq} dlen={dlen} chk={chk:02X} calc={calc:02X}"
        )
        raise ValueError(
            f"Header checksum mismatch: received 0x{chk:02X}, computed 0x{calc:02X}"
        )
    return {"service_type": svc, "sequence": seq, "data_length": dlen}


# ---------------------------------------------------------------------------
# BootloaderSession
# ---------------------------------------------------------------------------


class BootloaderSession:
    """
    A helper for E2E tests to speak to the BSW bootloader over a serial port.

    Usage::

        with BootloaderSession("/dev/ttyACM0") as bsw:
            bsw.send_command('1')
            ack = bsw.wait_for_ack(timeout=5)
            log = bsw.drain_debug_log(timeout=2)
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 5.0):
        self.port = port
        self.baudrate = baudrate
        self.default_timeout = timeout
        self._ser: Optional[serial.Serial] = None

    # ------------------------------------------------------------------ lifecycle

    def open(self) -> None:
        self._ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
        time.sleep(0.2)  # let the UART settle

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
            self._ser = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------ send helpers

    def _send(self, header: bytes, data: bytes = b"") -> None:
        assert self._ser and self._ser.is_open, "Serial port not open"
        self._ser.write(header)
        self._ser.flush()
        if data:
            time.sleep(0.01)
            self._ser.write(data)
            self._ser.flush()

        print(
            f"Sent packet: header={header.hex()} data={data.hex() if data else '(none)'}"
        )

    def send_command(self, command: str, sequence: int = 0) -> None:
        """Send a DEBUG_LOG telecommand (the BSW's 'command input' path)."""
        data = command.encode("utf-8")
        hdr = _build_header(PacketType.DEBUG_LOG, sequence, len(data), is_tc=True)
        self._send(hdr, data)

    def send_start_upload(self, total_size: int, sequence: int = 0) -> None:
        data = struct.pack("<I", total_size)
        hdr = _build_header(PacketType.START_UPLOAD, sequence, len(data))
        self._send(hdr, data)

    def send_data_chunk(self, chunk: bytes, sequence: int = 0) -> None:
        hdr = _build_header(PacketType.DATA_CHUNK, sequence, len(chunk))
        self._send(hdr, chunk)

    def send_end_upload(self, sequence: int = 0) -> None:
        hdr = _build_header(PacketType.END_UPLOAD, sequence, 0)
        self._send(hdr)

    # ------------------------------------------------------------------ receive helpers

    def _read_exact(self, n: int, timeout: float) -> bytes:
        """Read exactly *n* bytes, raising TimeoutError if not received in time."""
        buf = b""
        deadline = time.monotonic() + timeout
        while self._ser.in_waiting < n:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Timed out waiting for {n} bytes (got {len(buf)})")
            time.sleep(0.001)

        if self._ser.in_waiting >= n:
            buf = self._ser.read(n)
        return buf

    def _receive_packet(self, timeout: float) -> dict:
        """Block until one ECSS packet is received. Returns a dict with keys:
        service_type, sequence, data_length, data, raw_debug (str if DEBUG_LOG)."""
        hdr_bytes = self._read_exact(HEADER_SIZE, timeout)
        meta = _parse_header(hdr_bytes)
        data = b""
        if meta["data_length"] > 0:
            data = self._read_exact(meta["data_length"], timeout)
        meta["data"] = data
        if meta["service_type"] == PacketType.DEBUG_LOG:
            meta["raw_debug"] = data.decode("utf-8", errors="replace")
            print(f"[{time.monotonic():.3f}] Received DEBUG_LOG: {meta['raw_debug']}")
            # print("Raw DEBUG_LOG:", " ".join(f"0x{b:02X}" for b in data))
        return meta

    def wait_for_ack(
        self, expected_sequence: Optional[int] = None, timeout: Optional[float] = None
    ) -> dict:
        """Wait for an ACK packet; skip any DEBUG_LOG packets in between.

        Raises:
            NackReceived: if a NACK is received instead.
            TimeoutError: if timeout expires.
            AssertionError: if a non-ACK/non-DEBUG packet arrives.
        """
        t = timeout or self.default_timeout
        deadline = time.monotonic() + t
        while time.monotonic() < deadline:
            pkt = self._receive_packet(deadline - time.monotonic())
            if pkt["service_type"] == PacketType.DEBUG_LOG:
                continue  # ignore debug messages
            if pkt["service_type"] == PacketType.NACK:
                code = pkt["data"][0] if pkt["data"] else 0
                raise NackReceived(pkt["sequence"], code)
            if pkt["service_type"] == PacketType.ACK:
                if expected_sequence is not None:
                    assert pkt["sequence"] == expected_sequence, (
                        f"ACK sequence mismatch: expected {expected_sequence}, "
                        f"got {pkt['sequence']}"
                    )
                return pkt
            raise AssertionError(
                f"Unexpected packet type 0x{pkt['service_type']:02X} while waiting for ACK"
            )
        raise TimeoutError("Timed out waiting for ACK")

    def drain_debug_log(self, timeout: float = 1.0) -> list[str]:
        """Collect all DEBUG_LOG lines until no new data arrives for *timeout* seconds.

        Returns a list of decoded string messages.
        """
        lines: list[str] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                pkt = self._receive_packet(0.1)
            except TimeoutError:
                # No data in the 0.1s slice — keep waiting until outer deadline.
                continue
            except ValueError as e:
                # Invalid/corrupt header: the BSW has handed off to the ASW
                # which is sending non-ECSS bytes.  The stream is done.
                print(f"Invalid packet header: {e}")
                break
            if pkt["service_type"] == PacketType.DEBUG_LOG:
                lines.append(pkt.get("raw_debug", ""))
        return lines

    # ------------------------------------------------------------------ complete upload sequence

    def upload_image(
        self,
        image_data: bytes,
        start_sequence: int = 1,
        chunk_size: int = 256,
        verbose: bool = False,
        max_retries: int = 3,
    ) -> None:
        """Upload a fully prepared (header + signed) image binary with ACK per chunk.

        Mirrors UploaderThread.run() in uploader/main.py: each packet is retried
        up to *max_retries* times and a small inter-chunk delay is inserted so the
        firmware has time to process each chunk before the next one arrives.

        Raises NackReceived or TimeoutError on failure.
        """
        seq = start_sequence
        total = len(image_data)

        # START
        start_sent = False
        for attempt in range(max_retries):
            self.send_start_upload(total, seq)
            try:
                self.wait_for_ack(expected_sequence=seq)
                start_sent = True
                break
            except TimeoutError:
                if attempt < max_retries - 1:
                    time.sleep(0.5)
        if not start_sent:
            raise TimeoutError("Failed to send START packet after multiple retries")
        if verbose:
            print(f"  [upload] START acked (seq={seq})")
        seq += 1
        time.sleep(0.1)  # let firmware settle before first chunk

        # DATA chunks
        total_chunks = (total + chunk_size - 1) // chunk_size
        bytes_sent = 0
        for chunk_num, offset in enumerate(range(0, total, chunk_size), start=1):
            chunk = image_data[offset : offset + chunk_size]
            chunk_sent = False
            for attempt in range(max_retries):
                self.send_data_chunk(chunk, seq)
                try:
                    self.wait_for_ack(expected_sequence=seq)
                    chunk_sent = True
                    break
                except TimeoutError:
                    if attempt < max_retries - 1:
                        time.sleep(0.3)
            if not chunk_sent:
                raise TimeoutError(
                    f"Failed to send chunk {chunk_num}/{total_chunks} after {max_retries} retries"
                )
            bytes_sent += len(chunk)
            if verbose and chunk_num % 10 == 0:
                print(
                    f"  [upload] {bytes_sent}/{total} bytes (chunk {chunk_num}/{total_chunks})"
                )
            seq += 1
            time.sleep(0.05)  # inter-chunk delay

        # END
        end_sent = False
        for attempt in range(max_retries):
            self.send_end_upload(seq)
            try:
                self.wait_for_ack(expected_sequence=seq)
                end_sent = True
                break
            except TimeoutError:
                if attempt < max_retries - 1:
                    time.sleep(0.3)
        if not end_sent:
            raise TimeoutError("Failed to send END packet after multiple retries")
        if verbose:
            print(f"  [upload] END acked (seq={seq})")


# ---------------------------------------------------------------------------
# NackReceived exception
# ---------------------------------------------------------------------------

_NACK_DESCRIPTIONS = {
    1: "Failed to receive START packet header",
    2: "Wrong packet type (expected START_UPLOAD)",
    3: "START packet data length invalid",
    4: "Failed to receive START packet data",
    6: "Failed to receive DATA packet header",
    7: "Wrong packet type (expected DATA_CHUNK)",
    8: "Failed to receive chunk data",
    9: "Invalid image or version too low",
    10: "System not configured for update (option bytes need reconfiguration)",
    11: "System not configured for nominal mode",
    12: "System not configured for image swap",
}


class NackReceived(Exception):
    def __init__(self, sequence: int, error_code: int):
        self.sequence = sequence
        self.error_code = error_code
        self.description = _NACK_DESCRIPTIONS.get(
            error_code, f"Unknown error {error_code}"
        )
        super().__init__(
            f"NACK received at seq={sequence}: [{error_code}] {self.description}"
        )
