"""
conftest.py - pytest fixtures and shared setup/teardown for BSW E2E tests.

Configuration is read from environment variables so tests can be driven from
CI without touching source code. Runs natively on Windows using
STM32CubeProgrammer CLI and pyserial.

Required environment variables:
    SERIAL_PORT   - Windows COM port, e.g. COM6
    PRIVATE_KEY   - path to the ECDSA .pem (or ML-DSA .bin) private key whose
                    corresponding public key is compiled into the BSW firmware.

Optional environment variables:
    SERIAL_BAUDRATE    - default 115200
    ACK_TIMEOUT        - default 5.0  (seconds per packet exchange)
    STM32CUBEPROG_BIN  - full path to STM32_Programmer_CLI.exe
    KEY_TYPE           - "ecdsa" (default) or "mldsa"
    MLDSA_PARAM_SET    - "ML-DSA-44" (default) or "ML-DSA-65"
    IMAGE_PAYLOAD_SIZE - size of the synthetic raw image, default 256 bytes
"""

import os
import sys
import time
from pathlib import Path

import pytest

# Make the helpers package importable even when pytest is invoked from the
# repository root.
sys.path.insert(0, str(Path(__file__).parent))

from helpers import board, serial_comm
from helpers.image_factory import ImageFactory


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _env(key, default=""):
    return os.environ.get(key, default)


def _require_env(key):
    val = os.environ.get(key)
    if not val:
        pytest.skip(f"Environment variable {key!r} not set - skipping hardware tests")
    return val


# ---------------------------------------------------------------------------
# Session-scoped fixtures (set up once per pytest run)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def config():
    """Collect all configuration in one dict so tests can inspect it."""
    return {
        "serial_port":    _require_env("SERIAL_PORT"),
        "baudrate":       int(_env("SERIAL_BAUDRATE", "115200")),
        "ack_timeout":    float(_env("ACK_TIMEOUT", "5.0")),
        "private_key":    _require_env("PRIVATE_KEY"),
        "key_type":       _env("KEY_TYPE", "ecdsa"),
        "mldsa_param":    _env("MLDSA_PARAM_SET", "ML-DSA-44"),
        "image_size":     int(_env("IMAGE_PAYLOAD_SIZE", "256")),
    }


@pytest.fixture(scope="session")
def image_factory(config):
    """Return an ImageFactory pre-loaded with the test private key."""
    return ImageFactory(
        private_key_path=config["private_key"],
        mldsa_param_set=config["mldsa_param"],
        minimal_image_size=config["image_size"],
    )


# ---------------------------------------------------------------------------
# Function-scoped fixtures (run before/after each test)
# ---------------------------------------------------------------------------

@pytest.fixture
def bsw(config):
    """Open a BootloaderSession, yield it, then close it."""
    session = serial_comm.BootloaderSession(
        port=config["serial_port"],
        baudrate=config["baudrate"],
        timeout=config["ack_timeout"],
    )
    session.open()
    yield session
    session.close()


@pytest.fixture
def clean_flash(config):
    """Erase BOOT, UPDATE, and SWAP slots and reset the COMM/COUNTER words.

    Also ensures both BOOT and COUNTER sectors are write-protected (nominal
    state) before yielding – mirrors what setupSystemForNominal() does.

    Yields nothing; intended to be used as a bare fixture.
    """
    # 1. Erase image slots
    board.flash_erase_slot(board.BOOT_FLASH_ADDRESS)
    board.flash_erase_slot(board.UPDATE_FLASH_ADDRESS)
    board.flash_erase_slot(board.SWAP_FLASH_ADDRESS)

    # 2. Write nominal COMM status
    board.set_comm_status(board.COMM_STATUS_NOMINAL)

    # 3. Reset rollback counter to 0
    board.set_rollback_counter(0)

    # 4. Protect sectors (BOOT sector 5 + COUNTER sector 9)
    #    Only change option bytes if they are already wrong to avoid
    #    unnecessary resets (each OB_Launch triggers a system reset).
    boot_protected    = board.is_write_protected(board.OB_WRP_BOOT)
    counter_protected = board.is_write_protected(board.OB_WRP_COUNTER)
    if not boot_protected or not counter_protected:
        board.set_write_protection(
            protect_mask=board.OB_WRP_BOOT | board.OB_WRP_COUNTER
        )
        time.sleep(1.5)  # wait for reset after OB_Launch

    yield


@pytest.fixture
def nominal_state(clean_flash, image_factory):
    """Provide a BOOT slot with a valid version-1 image and nominal WRP.

    Layers on top of clean_flash so the sector is already erased and WRP set.
    Yields the image bytes for further inspection in tests.
    """
    img = image_factory.build(version=1)
    board.flash_image(board.BOOT_FLASH_ADDRESS, img)
    yield img


@pytest.fixture
def update_ready_state(nominal_state, image_factory):
    """Extend nominal_state by placing a version-2 image in the UPDATE slot.

    The caller still needs to send a '2' command to trigger the actual update
    flow; this fixture only sets up the flash content.
    Yields (boot_image, update_image).
    """
    update_img = image_factory.build(version=2)
    board.flash_image(board.UPDATE_FLASH_ADDRESS, update_img)
    yield nominal_state, update_img


# ---------------------------------------------------------------------------
# Utility helpers available to all tests
# ---------------------------------------------------------------------------

def reset_and_connect(config: dict) -> serial_comm.BootloaderSession:
    """Hard-reset the board and return an open BootloaderSession.

    Use this in tests that need a fresh reset *between* steps without the
    bsw fixture lifecycle getting in the way.
    """
    board.reset_board(delay=1.0)
    session = serial_comm.BootloaderSession(
        port=config["serial_port"],
        baudrate=config["baudrate"],
        timeout=config["ack_timeout"],
    )
    session.open()
    return session
