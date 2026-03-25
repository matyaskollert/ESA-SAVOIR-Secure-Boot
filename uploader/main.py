"""
STM32F4 Binary Uploader Application
A simple GUI application for uploading binary files to STM32F4 boards via UART.
"""
import sys
import time
import queue
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTextEdit, QProgressBar, QGroupBox,
    QSpinBox, QMessageBox, QCheckBox, QLineEdit, QRadioButton, QButtonGroup,
    QComboBox
)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont
import serial
import serial.tools.list_ports
from binary_processor import process_binary
from signature_ecdsa import ECDSASignature
from signature_mldsa import MLDSASignature
from ecss_packet import (ECSSPacket, PacketType, create_start_packet, 
                         create_data_packet, create_end_packet, create_command_packet)


class NackReceivedException(Exception):
    """Exception raised when NACK packet is received from firmware."""
    
    # Error code descriptions from firmware
    ERROR_DESCRIPTIONS = {
        1: "Failed to receive START packet header",
        2: "Wrong packet type (expected START_UPLOAD)",
        3: "START packet data length invalid (expected 4 bytes)",
        4: "Failed to receive START packet data",
        6: "Failed to receive DATA packet header",
        7: "Wrong packet type (expected DATA_CHUNK)",
        8: "Failed to receive chunk data",
        9: "Invalid image header or version too low (check magic number and version)",
        10: "System not configured for update - option bytes need reconfiguration",
        11: "System not configured for nominal mode",
        12: "System not configured for image swap",
    }
    
    def __init__(self, sequence, error_code):
        self.sequence = sequence
        self.error_code = error_code
        self.description = self.ERROR_DESCRIPTIONS.get(error_code, f"Unknown error code: {error_code}")
        super().__init__(f"NACK received for sequence {sequence}, error code: {error_code} - {self.description}")


class PacketReceiverThread(QThread):
    """Background thread for continuously receiving ECSS packets."""
    debug_message = Signal(str)  # Signal for debug log messages
    packet_received = Signal(object)  # Signal for other packets
    connection_lost = Signal()
    
    def __init__(self, serial_port):
        super().__init__()
        self.serial_port = serial_port
        self._is_running = True
        self.packet_queue = queue.Queue()  # Queue for non-debug packets
    
    def run(self):
        """Continuously read and parse ECSS packets."""
        while self._is_running:
            try:
                if not self.serial_port or not self.serial_port.is_open:
                    time.sleep(0.1)
                    continue
                
                if self.serial_port.in_waiting >= ECSSPacket.HEADER_SIZE:
                    # Read packet header
                    header_bytes = self.serial_port.read(ECSSPacket.HEADER_SIZE)
                    packet = ECSSPacket.unpack_header(header_bytes)
                    
                    # Read data if present
                    if packet.data_length > 0:
                        # Wait for data to arrive
                        timeout = time.time() + 1.0
                        while self.serial_port.in_waiting < packet.data_length:
                            if time.time() > timeout:
                                break
                            time.sleep(0.001)
                        
                        if self.serial_port.in_waiting >= packet.data_length:
                            packet.data = self.serial_port.read(packet.data_length)
                    
                    # Handle packet based on type
                    if packet.service_type == PacketType.DEBUG_LOG:
                        # Immediately emit debug messages
                        try:
                            message = packet.data.decode('utf-8', errors='replace')
                            self.debug_message.emit(message)
                        except:
                            self.debug_message.emit(f"[Debug data: {packet.data.hex()}]")
                    else:
                        # Queue other packets for processing
                        self.packet_queue.put(packet)
                        self.packet_received.emit(packet)
                else:
                    time.sleep(0.01)  # Small delay when no data
                    
            except Exception as e:
                if self._is_running:
                    self.debug_message.emit(f"[Receiver error: {str(e)}]")
                    self.connection_lost.emit()
                break
    
    def get_packet(self, timeout=None):
        """Get a packet from the queue.
        
        Args:
            timeout: Maximum time to wait for a packet (None = wait forever)
            
        Returns:
            ECSSPacket or None if timeout
        """
        try:
            return self.packet_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def stop(self):
        """Stop the receiver thread."""
        self._is_running = False


class UploaderThread(QThread):
    """Worker thread for handling the upload process."""
    progress = Signal(int)
    status = Signal(str)
    uart_data = Signal(str)  # Signal for UART data received from board
    finished = Signal(bool, str)
    
    def __init__(self, patched_file_path, receiver_thread, port='COM6', baudrate=115200):
        super().__init__()
        self.patched_file_path = patched_file_path
        self.receiver_thread = receiver_thread
        self.port = port
        self.baudrate = baudrate
        self._is_running = True
        self.ack_timeout = 2.0  # Timeout for ACK in seconds
        self.max_retries = 3  # Maximum number of retries per transmission
    
    def wait_for_ack_packet(self, expected_sequence):
        """Wait for ECSS ACK packet from the receiver thread queue.
        
        Args:
            expected_sequence: Expected sequence number in ACK
            
        Returns:
            bool: True if ACK received, False on timeout
            
        Raises:
            NackReceivedException: If NACK packet is received
        """
        start_time = time.time()
        while (time.time() - start_time) < self.ack_timeout:
            if not self._is_running:
                return False
            
            # Get packet from receiver queue (non-blocking with timeout)
            packet = self.receiver_thread.get_packet(timeout=0.1)
            
            if packet:
                # Handle different packet types
                if packet.service_type == PacketType.ACK:
                    if packet.sequence_count == expected_sequence:
                        return True
                    else:
                        self.uart_data.emit(f"[Warning: ACK seq mismatch: expected {expected_sequence}, got {packet.sequence_count}]")
                        return True  # Accept anyway for now
                elif packet.service_type == PacketType.NACK:
                    error_code = packet.data[0] if len(packet.data) > 0 else 0
                    # Raise exception to immediately stop upload
                    raise NackReceivedException(packet.sequence_count, error_code)
                else:
                    self.uart_data.emit(f"[Unexpected packet type: {packet.service_type}]")
                    # Put it back in queue if not ACK/NACK?
                    return False
            
        return False
        
    def run(self):
        """Execute the upload process using ECSS packet protocol."""
        try:
            # Use the serial port from the receiver thread
            ser = self.receiver_thread.serial_port
            
            if not ser or not ser.is_open:
                self.finished.emit(False, f"Serial port not open. Please connect to the device first.")
                return
            
            self.status.emit(f"Using connection on {self.port}...")
            
            # First send a "2" command as ECSS packet to signal the board to prepare for upload
            self.status.emit("Signaling board to prepare for upload...")
            command_packet = create_command_packet(0, '2')
            cmd_header = command_packet.pack_header()
            cmd_data = command_packet.data
            print(f"Sending command - Header: {cmd_header.hex()}, Data: {cmd_data.hex()}")
            
            # Send header first
            ser.write(cmd_header)
            ser.flush()
            # Small delay
            time.sleep(0.01)
            # Send data
            if len(cmd_data) > 0:
                ser.write(cmd_data)
                ser.flush()
            
            # Wait for ACK from firmware to confirm system is ready for upload
            self.status.emit("Waiting for board to confirm system configuration...")
            if not self.wait_for_ack_packet(0):
                self.finished.emit(False, "Board did not acknowledge upload command (timeout or system not configured)")
                return
            
            self.status.emit("Board ready for upload")
            time.sleep(0.5)  # Brief delay before starting upload

            # Read the binary file
            self.status.emit("Reading patched binary file...")
            with open(self.patched_file_path, 'rb') as f:
                binary_data = f.read()
            
            total_size = len(binary_data)
            self.status.emit(f"Uploading {total_size} bytes using ECSS protocol...")

            sequence = 0
            
            # 1. Send START_UPLOAD packet with total size
            self.status.emit(f"Sending START_UPLOAD packet...")
            start_packet = create_start_packet(sequence, total_size)
            start_header = start_packet.pack_header()
            start_data = start_packet.data
            print(f"START_UPLOAD - Header: {start_header.hex()}, Data: {start_data.hex()}")
            
            start_sent = False
            for attempt in range(self.max_retries):
                if not self._is_running:
                    self.finished.emit(False, "Upload cancelled by user")
                    return
                
                self.status.emit(f"Sending START packet... Attempt {attempt + 1}/{self.max_retries}")
                # Send header first
                ser.write(start_header)
                ser.flush()
                # Small delay to let firmware start receiving data
                time.sleep(0.01)
                # Send data
                if len(start_data) > 0:
                    ser.write(start_data)
                    ser.flush()
                
                # Wait for ACK
                if self.wait_for_ack_packet(sequence):
                    self.status.emit("START_UPLOAD acknowledged")
                    start_sent = True
                    break
                else:
                    self.status.emit(f"Timeout waiting for ACK (attempt {attempt + 1})")
                    if attempt < self.max_retries - 1:
                        time.sleep(0.5)
            
            if not start_sent:
                self.finished.emit(False, "Failed to send START packet after multiple retries")
                return

            sequence += 1

            # Check for any incoming messages from board
            time.sleep(0.1)
            if ser.in_waiting > ECSSPacket.HEADER_SIZE:
                # Skip potential non-packet data
                pass
            
            # 2. Send DATA_CHUNK packets
            chunk_size = 256
            bytes_sent = 0
            
            for i in range(0, total_size, chunk_size):
                if not self._is_running:
                    self.finished.emit(False, "Upload cancelled by user")
                    return
                
                chunk = binary_data[i:i + chunk_size]
                chunk_num = i // chunk_size + 1
                total_chunks = (total_size + chunk_size - 1) // chunk_size
                
                # Create DATA_CHUNK packet
                data_packet = create_data_packet(sequence, chunk)
                chunk_header = data_packet.pack_header()
                chunk_data = data_packet.data
                
                # Try to send chunk with retry
                chunk_sent = False
                for attempt in range(self.max_retries):
                    if not self._is_running:
                        self.finished.emit(False, "Upload cancelled by user")
                        return
                    
                    if attempt > 0:
                        self.status.emit(f"Retrying chunk {chunk_num}/{total_chunks}... Attempt {attempt + 1}/{self.max_retries}")
                    
                    # Send header first
                    ser.write(chunk_header)
                    ser.flush()
                    # Small delay to let firmware start receiving data
                    time.sleep(0.01)
                    # Send data
                    if len(chunk_data) > 0:
                        ser.write(chunk_data)
                        ser.flush()
                    
                    # Wait for ACK
                    if self.wait_for_ack_packet(sequence):
                        chunk_sent = True
                        break
                    else:
                        self.status.emit(f"Timeout waiting for ACK (attempt {attempt + 1})")
                        if attempt < self.max_retries - 1:
                            time.sleep(0.3)
                
                if not chunk_sent:
                    self.finished.emit(False, f"Failed to send chunk {chunk_num} after {self.max_retries} retries")
                    return
                
                bytes_sent += len(chunk)
                sequence += 1
                
                # Update progress
                progress_percent = int((bytes_sent / total_size) * 100)
                self.progress.emit(progress_percent)
                self.status.emit(f"Uploading: {bytes_sent}/{total_size} bytes ({progress_percent}%) - Chunk {chunk_num}/{total_chunks}")
                
                # Small delay between chunks
                time.sleep(0.05)
            
            # 3. Send END_UPLOAD packet
            self.status.emit("Sending END_UPLOAD packet...")
            end_packet = create_end_packet(sequence)
            end_header = end_packet.pack_header()
            
            for attempt in range(self.max_retries):
                if not self._is_running:
                    break
                
                # END packet has no data, just send header
                ser.write(end_header)
                ser.flush()
                
                if self.wait_for_ack_packet(sequence):
                    self.status.emit("END_UPLOAD acknowledged")
                    break
                else:
                    if attempt < self.max_retries - 1:
                        time.sleep(0.3)
            
            #Upload complete
            self.status.emit("Upload complete.")
            self.progress.emit(100)
            
            # Receiver thread continues to monitor
            time.sleep(1)
            
            self.finished.emit(True, f"Successfully uploaded {total_size} bytes using ECSS protocol!")
                
            # Note: Serial connection is owned by receiver thread, not closed here
                
        except NackReceivedException as e:
            # NACK received - firmware rejected the packet
            error_msg = f"Upload failed: Firmware sent NACK - {e.description}"
            self.status.emit("ERROR: " + error_msg)
            self.uart_data.emit(f"\n{'='*60}")
            self.uart_data.emit(f"FIRMWARE ERROR - UPLOAD ABORTED")
            self.uart_data.emit(f"Sequence Number: {e.sequence}")
            self.uart_data.emit(f"Error Code: {e.error_code}")
            self.uart_data.emit(f"Description: {e.description}")
            self.uart_data.emit(f"{'='*60}\n")
            self.finished.emit(False, error_msg)
        except Exception as e:
            self.finished.emit(False, f"Error during upload: {str(e)}")
    
    def stop(self):
        """Stop the upload process."""
        self._is_running = False


class CommandSenderThread(QThread):
    """Worker thread for sending a command packet and waiting for ACK/NACK."""
    finished = Signal(bool, str)  # success, message

    def __init__(self, serial_port, receiver_thread, command_text):
        super().__init__()
        self.serial_port = serial_port
        self.receiver_thread = receiver_thread
        self.command_text = command_text
        self.ack_timeout = 2.0

    def run(self):
        try:
            ser = self.serial_port
            if not ser or not ser.is_open:
                self.finished.emit(False, "Not connected to board!")
                return

            packet = create_command_packet(0, self.command_text)
            header = packet.pack_header()
            data = packet.data

            ser.write(header)
            ser.flush()
            time.sleep(0.01)
            if len(data) > 0:
                ser.write(data)
                ser.flush()

            # Wait for ACK/NACK
            start_time = time.time()
            while (time.time() - start_time) < self.ack_timeout:
                pkt = self.receiver_thread.get_packet(timeout=0.1)
                if pkt:
                    if pkt.service_type == PacketType.ACK:
                        self.finished.emit(True, f"ACK received (seq {pkt.sequence_count})")
                        return
                    elif pkt.service_type == PacketType.NACK:
                        error_code = pkt.data[0] if len(pkt.data) > 0 else 0
                        desc = NackReceivedException.ERROR_DESCRIPTIONS.get(error_code, f"Unknown error code: {error_code}")
                        self.finished.emit(False, f"NACK received - error {error_code}: {desc}")
                        return
                    else:
                        self.finished.emit(False, f"Unexpected packet type: {pkt.service_type}")
                        return

            self.finished.emit(False, "Timeout waiting for ACK")
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")


class ReconnectThread(QThread):
    """Periodically tries to re-open a serial port after connection loss."""
    reconnected = Signal(object)  # passes the new serial.Serial instance

    def __init__(self, port, baudrate=115200, interval_ms=1000):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.interval_ms = interval_ms
        self._is_running = True

    def run(self):
        while self._is_running:
            try:
                ser = serial.Serial(self.port, self.baudrate, timeout=1)
                time.sleep(0.3)  # let the port settle
                self.reconnected.emit(ser)
                return
            except serial.SerialException:
                pass
            self.msleep(self.interval_ms)

    def stop(self):
        self._is_running = False


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.selected_file = None
        self.patched_file = None
        self.uploader_thread = None
        self.command_thread = None
        self.receiver_thread = None
        self.reconnect_thread = None
        self.serial_port = None
        self.image_version = 1
        self.signature_algo = ECDSASignature()  # updated when process_file() runs
        self.keys_dir = Path(__file__).parent / "keys"
        
        self.setWindowTitle("STM32F4 Binary Uploader")
        self.setMinimumSize(700, 600)
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 10, 12, 10)
        
        # Title
        title_label = QLabel("STM32F4 Binary Uploader")
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Connection group
        connection_group = QGroupBox("0. Serial Connection")
        connection_layout = QVBoxLayout()
        connection_layout.setSpacing(6)
        connection_layout.setContentsMargins(8, 8, 8, 8)
        
        # COM port selection row
        port_layout = QHBoxLayout()
        port_label = QLabel("COM Port:")
        port_label.setMinimumWidth(80)
        
        self.com_port_combobox = QComboBox()
        self.com_port_combobox.setEditable(True)  # Allow custom input
        self.com_port_combobox.setMinimumHeight(26)
        self.populate_com_ports()
        
        self.refresh_ports_button = QPushButton("Refresh")
        self.refresh_ports_button.setMinimumHeight(26)
        self.refresh_ports_button.clicked.connect(self.populate_com_ports)
        
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.com_port_combobox, 1)
        port_layout.addWidget(self.refresh_ports_button)
        connection_layout.addLayout(port_layout)
        
        # Connect/Disconnect buttons row
        button_layout = QHBoxLayout()
        
        self.connect_button = QPushButton("Connect")
        self.connect_button.setMinimumHeight(28)
        self.connect_button.clicked.connect(self.connect_to_board)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setMinimumHeight(28)
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.clicked.connect(self.disconnect_from_board)
        
        self.connection_status_label = QLabel("Not connected")
        self.connection_status_label.setStyleSheet("color: #cc0000; font-weight: bold; padding: 5px;")
        
        button_layout.addWidget(self.connect_button)
        button_layout.addWidget(self.disconnect_button)
        button_layout.addWidget(self.connection_status_label, 1)
        connection_layout.addLayout(button_layout)
        
        connection_group.setLayout(connection_layout)
        main_layout.addWidget(connection_group)
        
        # File selection group
        file_group = QGroupBox("1. Select Binary File")
        file_layout = QVBoxLayout()
        file_layout.setContentsMargins(8, 8, 8, 8)
        
        file_select_layout = QHBoxLayout()
        self.select_button = QPushButton("Browse...")
        self.select_button.setMinimumHeight(28)
        self.select_button.clicked.connect(self.select_file)
        
        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet("padding: 5px; background-color: #f0f0f0; border-radius: 3px;")
        
        file_select_layout.addWidget(self.select_button)
        file_select_layout.addWidget(self.file_label, 1)
        file_layout.addLayout(file_select_layout)
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # Signature group
        sig_group = QGroupBox("2. Digital Signature")
        sig_layout = QVBoxLayout()
        sig_layout.setContentsMargins(8, 8, 8, 8)
        sig_layout.setSpacing(4)

        # ── Algorithm selector ──────────────────────────────────────────
        algo_layout = QHBoxLayout()
        algo_label = QLabel("Algorithm:")
        algo_label.setMinimumWidth(80)
        self.algo_button_group = QButtonGroup()
        self.ecdsa_algo_radio = QRadioButton("ECDSA-P256")
        self.mldsa_algo_radio = QRadioButton("ML-DSA (post-quantum)")
        self.ecdsa_algo_radio.setChecked(True)
        self.algo_button_group.addButton(self.ecdsa_algo_radio)
        self.algo_button_group.addButton(self.mldsa_algo_radio)

        # ML-DSA parameter-set drop-down (only visible when ML-DSA is selected)
        self.mldsa_params_combo = QComboBox()
        self.mldsa_params_combo.addItems(["ML-DSA-44", "ML-DSA-65"])
        self.mldsa_params_combo.setToolTip(
            "ML-DSA-44: 2420-byte sig, 1312-byte pk (NIST level 2)\n"
            "ML-DSA-65: 3309-byte sig, 1952-byte pk (NIST level 3)"
        )
        self.mldsa_params_combo.setEnabled(False)

        algo_layout.addWidget(algo_label)
        algo_layout.addWidget(self.ecdsa_algo_radio)
        algo_layout.addWidget(self.mldsa_algo_radio)
        algo_layout.addWidget(self.mldsa_params_combo)
        algo_layout.addStretch()
        sig_layout.addLayout(algo_layout)

        self.mldsa_algo_radio.toggled.connect(
            lambda checked: self.mldsa_params_combo.setEnabled(checked)
        )

        # ── Key options ─────────────────────────────────────────────────
        self.key_options_widget = QWidget()
        key_options_layout = QVBoxLayout(self.key_options_widget)
        key_options_layout.setContentsMargins(12, 0, 0, 0)
        key_options_layout.setSpacing(4)
        
        # Radio buttons for key generation/use
        self.key_button_group = QButtonGroup()
        self.generate_keys_radio = QRadioButton("Generate new keys")
        self.use_existing_keys_radio = QRadioButton("Use existing keys")
        self.generate_keys_radio.setChecked(True)
        self.key_button_group.addButton(self.generate_keys_radio)
        self.key_button_group.addButton(self.use_existing_keys_radio)
        key_options_layout.addWidget(self.generate_keys_radio)
        key_options_layout.addWidget(self.use_existing_keys_radio)
        
        # Existing keys path selection
        existing_keys_layout = QHBoxLayout()
        self.private_key_label = QLabel("Private Key:")
        self.private_key_path = QLineEdit()
        self.private_key_path.setPlaceholderText(
            "Path to private key (.pem for ECDSA, .bin for ML-DSA)"
        )
        self.private_key_browse = QPushButton("Browse...")
        self.private_key_browse.clicked.connect(self.browse_private_key)
        
        existing_keys_layout.addWidget(self.private_key_label)
        existing_keys_layout.addWidget(self.private_key_path, 1)
        existing_keys_layout.addWidget(self.private_key_browse)
        key_options_layout.addLayout(existing_keys_layout)
        
        # Connect radio button to enable/disable key path selection
        self.use_existing_keys_radio.toggled.connect(self.toggle_key_path_selection)
        
        sig_layout.addWidget(self.key_options_widget)
        
        sig_group.setLayout(sig_layout)
        main_layout.addWidget(sig_group)
        
        # Process group
        process_group = QGroupBox("3. Add Header and Process File")
        process_layout = QVBoxLayout()
        process_layout.setContentsMargins(8, 8, 8, 8)
        process_layout.setSpacing(6)
        
        # Version input
        version_layout = QHBoxLayout()
        version_label = QLabel("Image Version:")
        self.version_spinbox = QSpinBox()
        self.version_spinbox.setMinimum(1)
        self.version_spinbox.setMaximum(255)
        self.version_spinbox.setValue(1)
        self.version_spinbox.setMinimumWidth(100)
        version_layout.addWidget(version_label)
        version_layout.addWidget(self.version_spinbox)
        version_layout.addStretch()
        process_layout.addLayout(version_layout)
        
        self.process_button = QPushButton("Process File")
        self.process_button.setMinimumHeight(32)
        self.process_button.setEnabled(False)
        self.process_button.clicked.connect(self.process_file)
        
        process_layout.addWidget(self.process_button)
        process_group.setLayout(process_layout)
        main_layout.addWidget(process_group)
        
        # Status/Log group
        log_group = QGroupBox("Status Log")
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(8, 8, 8, 8)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(150)
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group, 1)
        
        # Command buttons group
        cmd_group = QGroupBox("Send Command to Board")
        cmd_layout = QVBoxLayout()
        cmd_layout.setContentsMargins(8, 8, 8, 8)
        cmd_layout.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.cmd_boot_btn      = QPushButton("1 - Boot")
        self.cmd_update_btn    = QPushButton("2 - Update")
        self.cmd_swap_btn      = QPushButton("3 - Swap")
        self.cmd_versions_btn  = QPushButton("4 - Check Versions")
        self.cmd_reset_btn     = QPushButton("5 - Reset")
        self.cmd_skip_btn      = QPushButton("6 - Skip Timeout")

        for btn, char in [
            (self.cmd_boot_btn,     '1'),
            (self.cmd_swap_btn,     '3'),
            (self.cmd_versions_btn, '4'),
            (self.cmd_reset_btn,    '5'),
            (self.cmd_skip_btn,     '6'),
        ]:
            btn.setMinimumHeight(32)
            btn.clicked.connect(lambda checked=False, c=char: self._send_command(c))

        self.cmd_update_btn.setMinimumHeight(32)
        self.cmd_update_btn.clicked.connect(self.upload_to_device)

        for btn in [self.cmd_boot_btn, self.cmd_update_btn, self.cmd_swap_btn,
                    self.cmd_versions_btn, self.cmd_reset_btn, self.cmd_skip_btn]:
            btn_row.addWidget(btn)

        cmd_layout.addLayout(btn_row)

        # Progress bar and cancel button (shown during upload)
        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(20)
        self.progress_bar.setValue(0)
        self.cancel_button = QPushButton("Cancel Upload")
        self.cancel_button.setMinimumHeight(26)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_upload)
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.cancel_button)
        cmd_layout.addLayout(progress_row)

        self._cmd_buttons = [
            self.cmd_boot_btn,  self.cmd_update_btn,
            self.cmd_swap_btn,  self.cmd_versions_btn,
            self.cmd_reset_btn, self.cmd_skip_btn,
        ]

        cmd_group.setLayout(cmd_layout)
        main_layout.addWidget(cmd_group)

        # ASW command group
        asw_group = QGroupBox("Send Command to ASW")
        asw_layout = QHBoxLayout()
        asw_layout.setContentsMargins(8, 8, 8, 8)
        asw_layout.setSpacing(6)

        asw_label = QLabel("Command:")
        self.asw_cmd_input = QLineEdit()
        self.asw_cmd_input.setPlaceholderText("1 = OK (set NOMINAL)   2 = FAULT (reset only)")
        self.asw_cmd_input.setMaxLength(1)
        self.asw_cmd_input.setFixedWidth(36)
        self.asw_send_btn = QPushButton("Send")
        self.asw_send_btn.setMinimumHeight(30)
        self.asw_send_btn.clicked.connect(self._send_asw_command)

        asw_layout.addWidget(asw_label)
        asw_layout.addWidget(self.asw_cmd_input)
        asw_layout.addWidget(self.asw_send_btn)
        asw_layout.addStretch()
        asw_group.setLayout(asw_layout)
        main_layout.addWidget(asw_group)

        self._cmd_buttons.append(self.asw_send_btn)
        
        # Initialize key path selection state
        self.toggle_key_path_selection()
        
        self.log("Application started. Select a .bin file to begin.")
    
    def toggle_key_path_selection(self):
        """Enable/disable key path selection based on radio button."""
        use_existing = self.use_existing_keys_radio.isChecked()
        self.private_key_label.setEnabled(use_existing)
        self.private_key_path.setEnabled(use_existing)
        self.private_key_browse.setEnabled(use_existing)
    
    def browse_private_key(self):
        """Browse for private key file."""
        if self.mldsa_algo_radio.isChecked():
            key_filter = "ML-DSA Key Files (*.bin);;All Files (*.*)"
        else:
            key_filter = "PEM Files (*.pem);;All Files (*.*)"

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Private Key File",
            str(self.keys_dir),
            key_filter
        )
        
        if file_path:
            self.private_key_path.setText(file_path)
            self.log(f"Selected private key: {file_path}")
    
    def process_file(self):
        """Process the binary file and add header with CRC and signature."""
        if not self.selected_file:
            self.log("ERROR: No file selected!")
            return
        
        try:
            # Get version from spinbox (applied each time Process is clicked)
            self.image_version = self.version_spinbox.value()
            self.log(f"Processing with image version: {self.image_version}")
            
            # Disable buttons during processing
            self.process_button.setEnabled(False)
            self.version_spinbox.setEnabled(False)

            # ── Construct the appropriate signature algorithm object ──────
            if self.mldsa_algo_radio.isChecked():
                param_set = self.mldsa_params_combo.currentText()
                self.signature_algo = MLDSASignature(parameter_set=param_set)
                key_ext = ".bin"
                algo_label = f"ML-DSA ({param_set})"
            else:
                self.signature_algo = ECDSASignature()
                key_ext = ".pem"
                algo_label = "ECDSA-P256"

            self.log(f"Setting up {algo_label} signature...")

            if self.generate_keys_radio.isChecked():
                # Generate new keys
                self.keys_dir.mkdir(exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                private_key_path = str(self.keys_dir / f"private_key_{timestamp}{key_ext}")
                public_key_path  = str(self.keys_dir / f"public_key_{timestamp}{key_ext}")

                self.log(f"Generating new {algo_label} key pair...")
                self.signature_algo.generate_keys(private_key_path, public_key_path)
                self.log(f"Keys saved to {self.keys_dir}")
            else:
                # Use existing keys
                private_key_path = self.private_key_path.text()
                if not private_key_path or not Path(private_key_path).exists():
                    self.log("ERROR: Private key file not found!")
                    self.process_button.setEnabled(True)
                    self.version_spinbox.setEnabled(True)
                    return

                self.log(f"Loading {algo_label} private key from {private_key_path}...")
                self.signature_algo.load_keys(private_key_path=private_key_path)
                self.log("Private key loaded")
            
            # Process the file with CRC and signature
            self.log(f"Processing binary file (version {self.image_version})...")
            self.patched_file = process_binary(
                self.selected_file, 
                signature_algo=self.signature_algo,
                image_version=self.image_version,
            )
            self.log(f"Created patched file: {self.patched_file}")
            self.log("Ready to upload. Click '2 - Update' to start the upload.")
            self.log("You can change the version and click Process again to create a new patched file.")
            
            # Enable buttons (allow re-processing with different version)
            self.process_button.setEnabled(True)
            self.version_spinbox.setEnabled(True)
            
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            self.process_button.setEnabled(True)
            self.version_spinbox.setEnabled(True)
    
    def upload_to_device(self):
        """Upload the processed file to the device."""
        if not self.patched_file:
            self.log("ERROR: No processed file available!")
            return
        
        if not self.receiver_thread or not self.serial_port:
            self.log("ERROR: Not connected to board!")
            return
        
        try:
            self.log(f"Starting upload of image version {self.image_version}...")
            
            # Disable buttons during upload
            self.select_button.setEnabled(False)
            self.process_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.progress_bar.setValue(0)
            
            # Start upload in background thread
            self.uploader_thread = UploaderThread(self.patched_file, self.receiver_thread)
            self.uploader_thread.progress.connect(self.update_progress)
            self.uploader_thread.status.connect(self.log)
            self.uploader_thread.uart_data.connect(self.log_uart_data)
            self.uploader_thread.finished.connect(self.upload_finished)
            self.uploader_thread.start()
            
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            self.reset_ui()
    
    def populate_com_ports(self):
        """Populate the COM port combobox with available ports."""
        current_text = self.com_port_combobox.currentText()
        self.com_port_combobox.clear()
        
        available_ports = [p.device for p in serial.tools.list_ports.comports()]
        if available_ports:
            self.com_port_combobox.addItems(available_ports)
            # Try to restore previous selection
            if current_text:
                index = self.com_port_combobox.findText(current_text)
                if index >= 0:
                    self.com_port_combobox.setCurrentIndex(index)
            # Only log if log_text widget exists (not during initial UI setup)
            if hasattr(self, 'log_text'):
                self.log(f"Found {len(available_ports)} COM port(s): {', '.join(available_ports)}")
        else:
            self.com_port_combobox.addItem("COM6")  # Default fallback
            if hasattr(self, 'log_text'):
                self.log("No COM ports detected. You can enter one manually.")
    
    def connect_to_board(self):
        """Connect to the board and start packet receiver thread."""
        port = self.com_port_combobox.currentText().strip()
        if not port:
            self.log("ERROR: Please select or enter a COM port")
            return
        
        try:
            baudrate = 115200
            
            # Check if already connected
            if self.serial_port and self.serial_port.is_open:
                self.log(f"Already connected to {self.serial_port.port}")
                return
            
            self.log(f"Attempting to connect to {port}...")
            
            # Try to open serial port
            self.serial_port = serial.Serial(port, baudrate, timeout=1)
            time.sleep(0.5)
            
            # Start packet receiver thread
            self.receiver_thread = PacketReceiverThread(self.serial_port)
            self.receiver_thread.debug_message.connect(self.log_uart_data)
            self.receiver_thread.connection_lost.connect(self.on_connection_lost)
            self.receiver_thread.start()
            
            self.log(f"✓ Connected to {port} at {baudrate} baud")
            self.log("Packet receiver thread started")
            
            # Update UI
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
            self.com_port_combobox.setEnabled(False)
            self.refresh_ports_button.setEnabled(False)
            self.connection_status_label.setText(f"Connected to {port}")
            self.connection_status_label.setStyleSheet("color: #00aa00; font-weight: bold; padding: 5px;")
            
        except serial.SerialException as e:
            self.log(f"ERROR: Failed to connect to {port}: {str(e)}")
            QMessageBox.critical(
                self,
                "Connection Error",
                f"Failed to open {port}\n\n{str(e)}\n\n"
                "Please check that:\n"
                "• The device is connected\n"
                "• The correct COM port is selected\n"
                "• No other application is using this port"
            )
        except Exception as e:
            self.log(f"ERROR: Unexpected error connecting to board: {str(e)}")
    
    def disconnect_from_board(self):
        """Disconnect from the board (also cancels any in-progress reconnect)."""
        try:
            # Stop reconnect thread if active
            if self.reconnect_thread and self.reconnect_thread.isRunning():
                self.reconnect_thread.stop()
                self.reconnect_thread.wait()
                self.reconnect_thread = None

            # Stop receiver thread
            if self.receiver_thread and self.receiver_thread.isRunning():
                self.receiver_thread.stop()
                self.receiver_thread.wait()
                self.receiver_thread = None
            
            # Close serial port
            if self.serial_port and self.serial_port.is_open:
                port_name = self.serial_port.port
                self.serial_port.close()
                self.serial_port = None
                self.log(f"✓ Disconnected from {port_name}")
            
            # Update UI
            self.connect_button.setEnabled(True)
            self.disconnect_button.setEnabled(False)
            self.com_port_combobox.setEnabled(True)
            self.refresh_ports_button.setEnabled(True)
            self.connection_status_label.setText("Not connected")
            self.connection_status_label.setStyleSheet("color: #cc0000; font-weight: bold; padding: 5px;")
            
        except Exception as e:
            self.log(f"ERROR: Error while disconnecting: {str(e)}")
    
    def on_connection_lost(self):
        """Handle connection loss - start automatic reconnect loop."""
        self.log("Connection to board lost! Attempting to reconnect...")

        # Clean up dead receiver and port
        if self.receiver_thread:
            self.receiver_thread.stop()
            self.receiver_thread = None
        if self.serial_port:
            try:
                self.serial_port.close()
            except Exception:
                pass
            self.serial_port = None

        port = self.com_port_combobox.currentText().strip()
        self.connection_status_label.setText(f"Reconnecting to {port}...")
        self.connection_status_label.setStyleSheet("color: #cc6600; font-weight: bold; padding: 5px;")
        # Keep Disconnect available so the user can cancel
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)

        self.reconnect_thread = ReconnectThread(port)
        self.reconnect_thread.reconnected.connect(self.on_reconnected)
        self.reconnect_thread.start()

    def on_reconnected(self, ser):
        """Called by ReconnectThread when the port is successfully reopened."""
        self.serial_port = ser
        port = ser.port

        self.receiver_thread = PacketReceiverThread(self.serial_port)
        self.receiver_thread.debug_message.connect(self.log_uart_data)
        self.receiver_thread.connection_lost.connect(self.on_connection_lost)
        self.receiver_thread.start()

        self.log(f"✓ Reconnected to {port}")
        self.connection_status_label.setText(f"Connected to {port}")
        self.connection_status_label.setStyleSheet("color: #00aa00; font-weight: bold; padding: 5px;")
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)

    def _send_command(self, char):
        """Send a single-character command to the board as an ECSS command packet."""
        if not self.serial_port or not self.serial_port.is_open:
            self.log("ERROR: Not connected to board!")
            return
        if not self.receiver_thread:
            self.log("ERROR: Receiver thread not running!")
            return

        try:
            labels = {'1': 'Boot', '2': 'Update', '3': 'Swap', '4': 'Check Versions', '5': 'Reset', '6': 'Skip Timeout'}
            self.log(f"Sending command: '{char}' ({labels.get(char, char)})")
            for btn in self._cmd_buttons:
                btn.setEnabled(False)

            self.command_thread = CommandSenderThread(self.serial_port, self.receiver_thread, char)
            self.command_thread.finished.connect(self.on_command_finished)
            self.command_thread.start()

        except Exception as e:
            self.log(f"Error sending command: {str(e)}")
            for btn in self._cmd_buttons:
                btn.setEnabled(True)

    def _send_asw_command(self):
        """Send the character typed in the ASW command input."""
        text = self.asw_cmd_input.text().strip()
        if not text:
            self.log("ERROR: Enter a command character first (e.g. '1' or '2').")
            return
        self._send_command(text[0])

    def on_command_finished(self, success, message):
        """Handle command send completion."""
        if success:
            self.log(f"\u2713 Command acknowledged: {message}")
        else:
            self.log(f"\u2717 Command failed: {message}")
        for btn in self._cmd_buttons:
            btn.setEnabled(True)
    
    def cancel_upload(self):
        """Cancel the ongoing upload."""
        if self.uploader_thread and self.uploader_thread.isRunning():
            self.log("Cancelling upload...")
            self.uploader_thread.stop()
            self.uploader_thread.wait()
    
    def update_progress(self, value):
        """Update the progress bar."""
        self.progress_bar.setValue(value)
    
    def upload_finished(self, success, message):
        """Handle upload completion."""
        self.log(message)
        if success:
            self.log("✓ Upload completed successfully!")
            self.progress_bar.setValue(100)
        else:
            self.log("✗ Upload failed!")
            # Show error message box if device not found
            if "not found" in message.lower() or "failed to open" in message.lower():
                QMessageBox.critical(
                    self,
                    "Connection Error",
                    "Unable to connect to the device.\n\n"
                    "Please check that:\n"
                    "• The STM32F4 board is connected\n"
                    "• The board is powered on\n"
                    "• The correct COM port (COM6) is selected\n"
                    "• No other application is using the port"
                )
        
        self.reset_ui()
    
    def reset_ui(self):
        """Reset UI elements to default state."""
        self.select_button.setEnabled(True)
        self.process_button.setEnabled(bool(self.selected_file))
        # Allow changing version whenever a file is selected (to re-process with different version)
        self.version_spinbox.setEnabled(bool(self.selected_file))
        self.cancel_button.setEnabled(False)
    
    def select_file(self):
        """Open file dialog to select a binary file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Binary File",
            "",
            "Binary Files (*.bin);;All Files (*.*)"
        )
        
        if file_path:
            self.selected_file = file_path
            self.file_label.setText(Path(file_path).name)
            self.process_button.setEnabled(True)
            self.log(f"Selected file: {file_path}")
    
    def log(self, message):
        """Add a message to the log."""
        self.log_text.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def log_uart_data(self, data):
        """Add UART data from board to the log with special formatting."""
        # Format UART data with a prefix to distinguish it
        self.log_text.append(f"<span style='color: #0066cc;'><b>[BOARD]</b> {data}</span>")
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def closeEvent(self, event):
        """Handle application close event."""
        if self.uploader_thread and self.uploader_thread.isRunning():
            self.uploader_thread.stop()
            self.uploader_thread.wait()
        
        # Disconnect from board
        self.disconnect_from_board()
        
        event.accept()


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
