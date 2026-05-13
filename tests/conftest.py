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
    MLDSA_PARAM_SET    - ML-DSA parameter set, must be "ML-DSA-65" (the only supported set)
    IMAGE_PAYLOAD_SIZE - size of the synthetic raw image, default 256 bytes
    REAL_ASW_BIN       - path to the raw (no-header) ASW binary, e.g.
                         example-asw/NucleoF439-ASW.bin.  When set, the
                         real_asw_image fixture signs it with the test key
                         so it can be flashed and booted in tests.
    REAL_ASW_VERSION   - version number embedded in the signed real-ASW image,
                         default 1
"""

import os
import sys
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env from the repository root (one level above tests/).  Values in
# .env are *not* overridden by variables that are already set in the shell,
# so real CI environment variables always take precedence.
load_dotenv(Path(__file__).parent / ".env", override=False)

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
        "serial_port": _require_env("SERIAL_PORT"),
        "baudrate": int(_env("SERIAL_BAUDRATE", "115200")),
        "ack_timeout": float(_env("ACK_TIMEOUT", "5.0")),
        "private_key": _require_env("PRIVATE_KEY"),
        "key_type": _env("KEY_TYPE", "ecdsa"),
        "mldsa_param": _env("MLDSA_PARAM_SET", "ML-DSA-65"),
        "image_size": int(_env("IMAGE_PAYLOAD_SIZE", "256")),
        "real_asw_bin": _env("REAL_ASW_BIN"),  # optional - may be ""
        "real_asw_version": int(_env("REAL_ASW_VERSION", "1")),
    }


@pytest.fixture(scope="session")
def image_factory(config):
    """Return an ImageFactory pre-loaded with the test private key."""
    return ImageFactory(
        private_key_path=config["private_key"],
        mldsa_param_set=config["mldsa_param"],
        minimal_image_size=config["image_size"],
    )


@pytest.fixture(scope="session")
def real_asw_image(config, image_factory):
    """Return a fully signed image built from the real ASW binary.

    The raw payload from REAL_ASW_BIN is wrapped with the BSW header
    (CRC + magic + version + signature) using the configured private key,
    producing a byte string ready to be flashed directly to the MAIN slot.

    Skips all tests that depend on this fixture when REAL_ASW_BIN is not set.
    """
    path = config["real_asw_bin"]
    if not path:
        pytest.skip("REAL_ASW_BIN not set - skipping real-ASW tests")
    raw = Path(path).read_bytes()
    return image_factory.build(version=config["real_asw_version"], image_payload=raw)


# ---------------------------------------------------------------------------
# Function-scoped fixtures (run before/after each test)
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=["slot_a_primary", "slot_b_primary"],
    ids=["primary=SLOT_A", "primary=SLOT_B"],
)
def slot_config(request):
    """Parametrized fixture: each test runs twice — once with SLOT_A as the
    primary (active) image slot, and once with SLOT_B as primary.

    Provides a namespace with:
        primary_flag        — PROTECTED_BSW_STATE value to write
        primary_address     — flash address of the primary slot
        secondary_address   — flash address of the secondary slot
        primary_ob_mask     — nWRP OB bitmask for the primary slot
        secondary_ob_mask   — nWRP OB bitmask for the secondary slot
        primary_slot_enum   — IMAGE_SLOT_A or IMAGE_SLOT_B (matches BSW report field)
    """
    from types import SimpleNamespace

    if request.param == "slot_a_primary":
        return SimpleNamespace(
            primary_flag=board.PROTECTED_BSW_STATE_PRIMARY_SLOT_A,
            primary_address=board.SLOT_A_FLASH_ADDRESS,
            secondary_address=board.SLOT_B_FLASH_ADDRESS,
            primary_ob_mask=board.OB_WRP_SLOT_A,
            secondary_ob_mask=board.OB_WRP_SLOT_B,
            primary_slot_enum=board.IMAGE_SLOT_A,
        )
    else:
        return SimpleNamespace(
            primary_flag=board.PROTECTED_BSW_STATE_PRIMARY_SLOT_B,
            primary_address=board.SLOT_B_FLASH_ADDRESS,
            secondary_address=board.SLOT_A_FLASH_ADDRESS,
            primary_ob_mask=board.OB_WRP_SLOT_B,
            secondary_ob_mask=board.OB_WRP_SLOT_A,
            primary_slot_enum=board.IMAGE_SLOT_B,
        )


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
def clean_flash(config, slot_config):
    """Erase SLOT_A and SLOT_B image slots, reset COMM/BSW-state words, and
    configure nominal write-protection (primary slot + PROTECTED_BSW_STATE protected).

    The primary slot is determined by the slot_config parametrized fixture so
    tests run for both SLOT_A-primary and SLOT_B-primary configurations.
    Mirrors what setupSystemForNominal() does on real hardware.

    Yields nothing; intended to be used as a bare fixture.
    """
    # 1. Erase image slots
    board.flash_erase_slot(board.SLOT_A_FLASH_ADDRESS)
    board.flash_erase_slot(board.SLOT_B_FLASH_ADDRESS)

    # 2. Erase report sector so each test starts with no stored reports
    board.erase_reports()

    # 3. Write nominal COMM status
    board.set_comm_status(board.COMM_STATUS_NOMINAL)

    # 4. Reset protected BSW state: counter=0, primary per slot_config
    board.set_rollback_counter(0)
    board.set_primary_flag(slot_config.primary_flag)

    # 5. Protect primary slot + PROTECTED_BSW_STATE; unprotect secondary slot.
    #    Only change option bytes if they are already wrong to avoid
    #    unnecessary resets (each OB_Launch triggers a system reset).
    primary_protected = board.is_write_protected(slot_config.primary_ob_mask)
    state_protected = board.is_write_protected(board.OB_WRP_PROTECTED_BSW_STATE)
    secondary_unprotected = not board.is_write_protected(slot_config.secondary_ob_mask)
    if not primary_protected or not state_protected or not secondary_unprotected:
        board.set_write_protection(
            protect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
            unprotect_mask=slot_config.secondary_ob_mask,
        )
    yield


@pytest.fixture
def nominal_state(clean_flash, slot_config, image_factory):
    """Provide the primary slot with a valid version-1 image and nominal WRP.

    Layers on top of clean_flash so the sector is already erased and WRP set.
    The primary slot is determined by slot_config.
    Yields the image bytes for further inspection in tests.
    """
    img = image_factory.build(version=1)
    board.flash_image(slot_config.primary_address, img)
    board.set_primary_flag(slot_config.primary_flag)
    yield img


@pytest.fixture
def real_asw_state(clean_flash, slot_config, real_asw_image):
    """Flash the real signed ASW image to the primary slot with nominal WRP.

    Depends on real_asw_image (session-scoped); the whole test is skipped
    automatically when REAL_ASW_BIN is not configured.
    The primary slot is determined by slot_config.
    Yields the signed image bytes.
    """
    board.flash_image(slot_config.primary_address, real_asw_image)
    board.set_primary_flag(slot_config.primary_flag)
    yield real_asw_image


@pytest.fixture
def update_ready_state(nominal_state, slot_config, image_factory):
    """Extend nominal_state by placing a version-2 image in the secondary slot.

    The primary slot is set by nominal_state/slot_config; the secondary slot
    holds the candidate image to be promoted via a swap command.
    The caller still needs to send a '2' command to trigger the actual update
    flow; this fixture only sets up the flash content.
    Yields (boot_image, update_image).
    """
    update_img = image_factory.build(version=2)
    board.flash_image(slot_config.secondary_address, update_img)
    yield nominal_state, update_img


@pytest.fixture
def swap_ready_state(clean_flash, slot_config, image_factory):
    """Primary=v1, Secondary=v2, COMM=SWAP(0xCC),
    WRP unlocked for the primary slot and PROTECTED_BSW_STATE.

    Mirrors the state left by a successful upload + setupSystemForImageSwap():
      - Primary slot has a valid signed v1 image (current primary)
      - Secondary slot has a valid signed v2 image (upload target, future primary)
      - primary_slot flag set per slot_config
      - COMM status word = 0xCC (SWAP)
      - Primary slot and PROTECTED_BSW_STATE (sector 9) write-protection lifted

    Yields (primary_image_bytes, secondary_image_bytes).
    """
    primary_img = image_factory.build(version=1)
    secondary_img = image_factory.build(version=2)
    board.flash_image(slot_config.primary_address, primary_img)
    board.flash_image(slot_config.secondary_address, secondary_img)
    board.set_rollback_counter(1)
    board.set_primary_flag(slot_config.primary_flag)
    board.set_comm_status(board.COMM_STATUS_SWAP)
    board.set_write_protection(
        protect_mask=0,
        unprotect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
    )
    yield primary_img, secondary_img


@pytest.fixture
def interrupted_swap_state(clean_flash, slot_config, image_factory):
    """Simulate a power cut between a completed upload and the swap command.

    The BSW has already run setupSystemForImageSwap() (COMM=0xCC, sectors
    unlocked) but the board was reset before '3' was issued.  The primary slot
    still contains v1; the secondary slot contains the freshly uploaded v2.

    Identical to swap_ready_state; named separately to make intent explicit
    in lifecycle tests.
    Yields (primary_image_bytes, secondary_image_bytes).
    """
    primary_img = image_factory.build(version=1)
    secondary_img = image_factory.build(version=2)
    board.flash_image(slot_config.primary_address, primary_img)
    board.flash_image(slot_config.secondary_address, secondary_img)
    board.set_rollback_counter(1)
    board.set_primary_flag(slot_config.primary_flag)
    board.set_comm_status(board.COMM_STATUS_SWAP)
    board.set_write_protection(
        protect_mask=0,
        unprotect_mask=slot_config.primary_ob_mask | board.OB_WRP_PROTECTED_BSW_STATE,
    )
    yield primary_img, secondary_img


# ---------------------------------------------------------------------------
# Utility helpers available to all tests
# ---------------------------------------------------------------------------


def reset_and_connect(config: dict) -> serial_comm.BootloaderSession:
    """Hard-reset the board and return an open BootloaderSession.

    Use this in tests that need a fresh reset *between* steps without the
    bsw fixture lifecycle getting in the way.
    """
    board.reset_board()
    session = serial_comm.BootloaderSession(
        port=config["serial_port"],
        baudrate=config["baudrate"],
        timeout=config["ack_timeout"],
    )
    session.open()
    return session
