"""
STM32F4 Binary Uploader Application
A simple GUI application for uploading binary files to STM32F4 boards via UART.
"""
import sys
import time
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTextEdit, QProgressBar, QGroupBox,
    QSpinBox, QMessageBox, QCheckBox, QLineEdit, QRadioButton, QButtonGroup
)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont
import serial
import serial.tools.list_ports
from binary_processor import process_binary
from signature_ecdsa import ECDSASignature


class UploaderThread(QThread):
    """Worker thread for handling the upload process."""
    progress = Signal(int)
    status = Signal(str)
    uart_data = Signal(str)  # Signal for UART data received from board
    finished = Signal(bool, str)
    
    def __init__(self, patched_file_path, port='COM3', baudrate=115200):
        super().__init__()
        self.patched_file_path = patched_file_path
        self.port = port
        self.baudrate = baudrate
        self._is_running = True
        self.ack_timeout = 2.0  # Timeout for ACK in seconds
        self.max_retries = 3  # Maximum number of retries per transmission
    
    def wait_for_ack(self, ser):
        """Wait for ACK byte (0x06) from the microcontroller.
        
        Args:
            ser: Serial connection object
            
        Returns:
            bool: True if ACK received, False otherwise
        """
        start_time = time.time()
        while (time.time() - start_time) < self.ack_timeout:
            if ser.in_waiting > 0:
                data = ser.read(1)
                if data == b'\x06':  # ACK byte
                    return True
                else:
                    # Log unexpected byte
                    try:
                        text = data.decode('utf-8', errors='replace')
                        self.uart_data.emit(f"[Unexpected: {text}]")
                    except:
                        self.uart_data.emit(f"[Unexpected HEX: {data.hex()}]")
            time.sleep(0.01)  # Small delay to avoid busy-waiting
        return False
        
    def run(self):
        """Execute the upload process."""
        try:
            self.status.emit(f"Connecting to device on {self.port}...")
            
            # Try to connect to the serial port
            max_wait_time = 5  # seconds - shorter wait time
            start_time = time.time()
            ser = None
            
            while self._is_running and (time.time() - start_time) < max_wait_time:
                try:
                    ports = [p.device for p in serial.tools.list_ports.comports()]
                    if self.port in ports:
                        self.status.emit(f"Device detected on {self.port}. Opening connection...")
                        ser = serial.Serial(self.port, self.baudrate, timeout=1)
                        time.sleep(0.5)  # Give the connection time to stabilize
                        break
                except (serial.SerialException, OSError) as e:
                    time.sleep(0.5)
                    continue
            
            if not ser or not ser.is_open:
                self.finished.emit(False, f"Device not found on {self.port}. Please check connection and ensure the board is ready.")
                return
            
            try:
                # First send a "2" to signal the board to prepare for upload
                self.status.emit("Signaling board to prepare for upload...")
                ser.write(b'2')
                time.sleep(1)  # Wait for board to process

                # Read the binary file
                self.status.emit("Reading patched binary file...")
                with open(self.patched_file_path, 'rb') as f:
                    binary_data = f.read()
                
                total_size = len(binary_data)
                self.status.emit(f"Uploading {total_size} bytes to device...")

                # Send data size first (4 bytes, little-endian) with retry
                size_sent = False
                for attempt in range(self.max_retries):
                    if not self._is_running:
                        self.finished.emit(False, "Upload cancelled by user")
                        return
                    
                    self.status.emit(f"Sending data size ({total_size} bytes)... Attempt {attempt + 1}/{self.max_retries}")
                    ser.write(total_size.to_bytes(4, byteorder='little'))
                    
                    # Wait for ACK
                    if self.wait_for_ack(ser):
                        self.status.emit("Data size acknowledged by device")
                        size_sent = True
                        break
                    else:
                        self.status.emit(f"No ACK received for data size (attempt {attempt + 1})")
                        if attempt < self.max_retries - 1:
                            time.sleep(0.5)  # Wait before retry
                
                if not size_sent:
                    self.finished.emit(False, "Failed to send data size after multiple retries")
                    return

                # Check for any incoming messages from board
                time.sleep(0.1)
                if ser.in_waiting > 0:
                    incoming = ser.read(ser.in_waiting)
                    try:
                        text = incoming.decode('utf-8', errors='replace')
                        self.uart_data.emit(text)
                    except:
                        self.uart_data.emit(f"[HEX: {incoming.hex()}]")
                
                # Send the data in chunks
                chunk_size = 256
                bytes_sent = 0
                
                for i in range(0, total_size, chunk_size):
                    if not self._is_running:
                        self.finished.emit(False, "Upload cancelled by user")
                        return
                    
                    chunk = binary_data[i:i + chunk_size]
                    chunk_num = i // chunk_size + 1
                    total_chunks = (total_size + chunk_size - 1) // chunk_size
                    
                    # Try to send chunk with retry
                    chunk_sent = False
                    for attempt in range(self.max_retries):
                        if not self._is_running:
                            self.finished.emit(False, "Upload cancelled by user")
                            return
                        
                        if attempt > 0:
                            self.status.emit(f"Retrying chunk {chunk_num}/{total_chunks}... Attempt {attempt + 1}/{self.max_retries}")
                        
                        ser.write(chunk)
                        
                        # Wait for ACK
                        if self.wait_for_ack(ser):
                            chunk_sent = True
                            break
                        else:
                            self.status.emit(f"No ACK for chunk {chunk_num} (attempt {attempt + 1})")
                            if attempt < self.max_retries - 1:
                                time.sleep(0.3)  # Wait before retry
                    
                    if not chunk_sent:
                        self.finished.emit(False, f"Failed to send chunk {chunk_num} after {self.max_retries} retries")
                        return
                    
                    bytes_sent += len(chunk)
                    
                    # Update progress
                    progress_percent = int((bytes_sent / total_size) * 100)
                    self.progress.emit(progress_percent)
                    self.status.emit(f"Uploading: {bytes_sent}/{total_size} bytes ({progress_percent}%) - Chunk {chunk_num}/{total_chunks}")
                    
                    # Small delay between chunks
                    time.sleep(0.05)
                
                # Upload complete - continue monitoring UART output
                self.status.emit("Upload complete. Monitoring board output...")
                self.progress.emit(100)
                
                # Monitor UART for 10 seconds after upload
                monitor_time = 10
                start_monitor = time.time()
                
                while self._is_running and (time.time() - start_monitor) < monitor_time:
                    if ser.in_waiting > 0:
                        incoming = ser.read(ser.in_waiting)
                        try:
                            text = incoming.decode('utf-8', errors='replace')
                            self.uart_data.emit(text)
                        except:
                            self.uart_data.emit(f"[HEX: {incoming.hex()}]")
                    time.sleep(0.1)
                
                self.finished.emit(True, f"Successfully uploaded {total_size} bytes!")
                
            finally:
                ser.close()
                self.status.emit("Serial connection closed")
                
        except Exception as e:
            self.finished.emit(False, f"Error during upload: {str(e)}")
    
    def stop(self):
        """Stop the upload process."""
        self._is_running = False


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.selected_file = None
        self.patched_file = None
        self.uploader_thread = None
        self.image_version = 1
        self.signature_algo = ECDSASignature()
        self.keys_dir = Path(__file__).parent / "keys"
        
        self.setWindowTitle("STM32F4 Binary Uploader")
        self.setMinimumSize(700, 700)
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel("STM32F4 Binary Uploader")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # File selection group
        file_group = QGroupBox("1. Select Binary File")
        file_layout = QVBoxLayout()
        
        file_select_layout = QHBoxLayout()
        self.select_button = QPushButton("Browse...")
        self.select_button.setMinimumHeight(35)
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
        
        # Key options container
        self.key_options_widget = QWidget()
        key_options_layout = QVBoxLayout(self.key_options_widget)
        key_options_layout.setContentsMargins(20, 0, 0, 0)
        
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
        self.private_key_path.setPlaceholderText("Path to private key (.pem)")
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
        self.process_button.setMinimumHeight(40)
        self.process_button.setEnabled(False)
        self.process_button.clicked.connect(self.process_file)
        
        process_layout.addWidget(self.process_button)
        process_group.setLayout(process_layout)
        main_layout.addWidget(process_group)
        
        # Upload group
        upload_group = QGroupBox("4. Upload to Device")
        upload_layout = QVBoxLayout()
        
        # Upload and cancel buttons
        self.upload_button = QPushButton("UPLOAD to COM3")
        self.upload_button.setMinimumHeight(40)
        self.upload_button.setEnabled(False)
        self.upload_button.clicked.connect(self.upload_to_device)
        
        self.cancel_button = QPushButton("Cancel Upload")
        self.cancel_button.setMinimumHeight(35)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_upload)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.upload_button, 2)
        button_layout.addWidget(self.cancel_button, 1)
        upload_layout.addLayout(button_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(25)
        self.progress_bar.setValue(0)
        upload_layout.addWidget(self.progress_bar)
        
        upload_group.setLayout(upload_layout)
        main_layout.addWidget(upload_group)
        
        # Status/Log group
        log_group = QGroupBox("Status Log")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group, 1)
        
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
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Private Key File",
            str(self.keys_dir),
            "PEM Files (*.pem);;All Files (*.*)"
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
            # Get version from spinbox
            self.image_version = self.version_spinbox.value()
            
            # Disable buttons during processing
            self.process_button.setEnabled(False)
            self.version_spinbox.setEnabled(False)
            
            # Setup signature
            self.log("Setting up ECDSA signature...")
            
            if self.generate_keys_radio.isChecked():
                # Generate new keys
                self.keys_dir.mkdir(exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                private_key_path = str(self.keys_dir / f"private_key_{timestamp}.pem")
                public_key_path = str(self.keys_dir / f"public_key_{timestamp}.pem")
                
                self.log(f"Generating new ECDSA key pair...")
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
                
                self.log(f"Loading private key from {private_key_path}...")
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
            self.log("Ready to upload. Click UPLOAD.")
            
            # Enable upload button
            self.upload_button.setEnabled(True)
            
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
        
        try:
            self.log(f"Starting upload of image version {self.image_version}...")
            
            # Disable buttons during upload
            self.select_button.setEnabled(False)
            self.process_button.setEnabled(False)
            self.upload_button.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.progress_bar.setValue(0)
            
            # Start upload in background thread
            self.uploader_thread = UploaderThread(self.patched_file)
            self.uploader_thread.progress.connect(self.update_progress)
            self.uploader_thread.status.connect(self.log)
            self.uploader_thread.uart_data.connect(self.log_uart_data)
            self.uploader_thread.finished.connect(self.upload_finished)
            self.uploader_thread.start()
            
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            self.reset_ui()
    
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
                    "• The correct COM port (COM3) is selected\n"
                    "• No other application is using the port"
                )
        
        self.reset_ui()
    
    def reset_ui(self):
        """Reset UI elements to default state."""
        self.select_button.setEnabled(True)
        self.process_button.setEnabled(bool(self.selected_file))
        self.upload_button.setEnabled(bool(self.patched_file))
        self.version_spinbox.setEnabled(bool(self.selected_file) and not bool(self.patched_file))
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
        event.accept()


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
