# Secure Boot — STM32F439 Proof of Concept

A hardware-in-the-loop secure boot and firmware update proof of concept for the
**Nucleo-F439ZI** (STM32F439ZI, Cortex-M4 @ 168 MHz).  The system demonstrates
authenticated firmware updates using classic and post-quantum signature algorithms
via wolfSSL, a UART-based ECSS-inspired upload protocol, and a pytest E2E test
suite that exercises every BSW path from flash validation to option-byte enforcement.

---

## Repository Layout

```
.
+-- STM32CubeIDE/
¦   +-- NucleoF439-BSW/          # Boot Software (BSW) — the secure bootloader
¦   +-- NucleoF439-BSP/          # Board Support Package — shared HAL drivers, protocol, flash
¦   +-- NucleoF439-ASW/          # Example Application Software (ASW)
¦   +-- NucleoF439-Benchmark/    # On-target signature benchmark firmware
+-- benchmark_tool/              # Host-side signing benchmark (C + wolfSSL)
+-- uploader/                    # GUI firmware uploader (Python / PySide6)
+-- tests/                       # Hardware-in-the-loop pytest test suite
+-- example-asw/                 # Pre-built ASW binary used by the test suite
+-- ECSS_PROTOCOL.md             # Wire-format specification for the upload protocol
+-- TEST_SUITE_DESCRIPTION.md    # Detailed description of every test case
```

---

## Hardware and Flash Layout

| Region              | Address      | Sector | Size   | Purpose                                     |
|---------------------|--------------|--------|--------|---------------------------------------------|
| BSW (bootloader)    | 0x08000000   | 0–4    | 128 KB | Secure bootloader — never overwritten        |
| SLOT_A              | 0x08020000   | 5      | 128 KB | First application image slot                 |
| SLOT_B              | 0x08040000   | 6      | 128 KB | Second application image slot                |
| SWAP                | 0x08060000   | 7      | 128 KB | Temporary buffer during hardware image swap  |
| COMM                | 0x08080000   | 8      | 128 KB | Boot-mode word shared between BSW and ASW    |
| PROTECTED_BSW_STATE | 0x080A0000   | 9      | 128 KB | Rollback counter + primary slot flag         |
| REPORT              | 0x080C0000   | 10     | 128 KB | Circular log of up to 5 BSW event reports    |

Write protection (STM32 nWRP option bytes) is enforced at the sector level.
The BSW reconfigures protection automatically as part of lifecycle management.

> **Swap modes:** The BSW supports two swap strategies selected at build time:
>
> - **Software swap (default):** No data is moved.  The `primary_slot` field in
>   `PROTECTED_BSW_STATE` is updated to point to the other partition, and the
>   BSW boots from whichever slot it identifies as primary on the next reset.
> - **Hardware swap:** The image bytes are physically relocated between sectors:
>   the current primary image is copied to SWAP, the update image is copied into
>   the primary slot, and the SWAP contents are written to the update slot
>   (`primary → SWAP → update → primary`).  After the swap the same slot is
>   always booted, but it now contains the new image.

---

## Build-Time Configuration

All flags are passed as preprocessor defines (`-D<FLAG>`) in STM32CubeIDE under
*Project → Properties → C/C++ Build → Settings → MCU GCC Compiler → Preprocessor*.

### BSW (`NucleoF439-BSW`)

| Define | Default | Effect |
|--------|---------|--------|
| *(none)* | ECDSA-P256, software swap | Classical ECDSA-P256 signature verification; swap changes only the `primary_slot` pointer in `PROTECTED_BSW_STATE` |
| `POST_QUANTUM` | — | Use ML-DSA-65 (Dilithium level 3) instead of ECDSA-P256 for signature verification |
| `HYBRID` | — | Verify both ECDSA-P256 **and** ML-DSA-65; both must pass (ECDSA first, then ML-DSA) |
| `HARDWARE_SWAP` | — | During a swap, physically relocate image bytes between flash sectors (`primary → SWAP → update → primary`) instead of just flipping the `primary_slot` pointer |

`POST_QUANTUM` and `HYBRID` are mutually exclusive.  `HYBRID` takes precedence
if both are defined.  The uploader and test suite must use a key and `KEY_TYPE`
that matches the define active in the flashed BSW.

### Benchmark firmware (`NucleoF439-Benchmark`)

| Define | Example value | Effect |
|--------|---------------|--------|
| `BENCHMARK_ALGO` | `BENCHMARK_ALGO_ECDSA_P256` | Selects the algorithm exercised by the on-target benchmark; see `benchmark.h` for the full list of `BENCHMARK_ALGO_*` constants |

#### Hardware vs. software hashing

The STM32F439 has a hardware SHA-256 accelerator.  By default the wolfSSL
configuration (`wolfSSL.I-CUBE-wolfSSL_conf.h`) uses it (`NO_STM32_HASH` is
*not* defined, because the platform block `#undef`s it for `STM32F439xx`).

To benchmark **software hashing** instead — and isolate the pure CPU cost —
uncomment the override near the bottom of the config file:

```c
// In wolfSSL.I-CUBE-wolfSSL_conf.h (near the end of the file):
#define NO_STM32_HASH   // <-- uncomment this line
```

This forces wolfCrypt to use its portable C SHA-256 implementation regardless of
the platform section, letting you directly compare HW-accelerated vs.
software-only timings for the same algorithm.

---

## Image Header Format

Every signed image starts with a 5 120-byte header partition:

```
Offset   Size   Field
     0      4   CRC-32/MPEG-2 of the payload (computed over bytes after the header)
     4      2   Magic: 0xABCD
     6      2   Image version (uint16, monotonically increasing)
     8      4   Payload size in bytes
    12   4096   Digital signature (algorithm-specific, zero-padded)
  4108      ~   Raw application payload (ARM vector table at the front)
```

---

## BSW Boot Sequence

On power-up the BSW:

1. Checks write-protection state of all managed sectors (`checkSystemForNominal`).
2. Sets the COMM word to `NOMINAL (0xAA)` in flash.
3. Verifies the Flash CRC of the primary image.
4. Verifies the digital signature of the primary image with wolfSSL.
5. Copies the image to RAM and verifies the RAM CRC.
6. Writes a `NOMINAL` event report to the REPORT sector.
7. Jumps to the application entry point.

Any failure writes a report with the appropriate outcome code and either resets
or halts depending on the failure type.  See `TEST_SUITE_DESCRIPTION.md` for the
full outcome-code table.

---

## Supported Signature Algorithms

| Algorithm       | Library       | Signature size | Security level       |
|-----------------|---------------|----------------|----------------------|
| ECDSA-P256      | wolfSSL ECC   | ~72 B          | Classical — 128-bit  |
| RSA-2048-PSS    | wolfSSL RSA   | 256 B          | Classical            |
| RSA-3072-PSS    | wolfSSL RSA   | 384 B          | Classical            |
| RSA-4096-PSS    | wolfSSL RSA   | 512 B          | Classical            |
| ML-DSA-65       | wolfSSL PQC   | 3 309 B        | Post-quantum level 3 |
| LMS-SHA256-H5   | wolfSSL LMS   | ~1 292 B       | Post-quantum (hash)  |

The BSW firmware is compiled with a **single algorithm selected at build time**
via wolfSSL defines.  The uploader and test suite select the matching algorithm
at runtime via the `KEY_TYPE` environment variable.

---

## Prerequisites

### Firmware build

| Tool | Version tested |
|------|----------------|
| STM32CubeIDE | 1.19.0 |
| ARM GCC (bundled) | 13.3.1 (`arm-none-eabi-gcc`) |
| STM32CubeProgrammer | latest |

### Host tools

| Tool | Minimum version |
|------|-----------------|
| Python | 3.11 |
| PySide6 | 6.6 (uploader GUI) |
| pyserial | 3.5 |
| cryptography | 41.0 |
| wolfcrypt-py | latest (ML-DSA / LMS signing) |
| pytest | 8.0 (test suite) |
| python-dotenv | 1.0 (test suite) |

> **wolfcrypt-py:** The ML-DSA and LMS signing backends depend on
> [wolfcrypt-py](https://github.com/wolfSSL/wolfcrypt-py).  Installation is
> non-trivial — the Python binding must be linked against a wolfCrypt C library
> that was compiled with Dilithium and LMS support enabled.  You will likely
> need to either modify the `wolfcrypt-py` build scripts or point them at your
> own wolfCrypt installation manually.  Refer to the wolfcrypt-py repository for
> detailed build instructions.

---

## Building the Firmware

1. Open STM32CubeIDE and import all projects from `STM32CubeIDE/`
   (*File ? Import ? Existing Projects into Workspace*).
2. Build **NucleoF439-BSP** first (it is a static library referenced by the other projects).
3. Build **NucleoF439-BSW** (bootloader).
4. Build **NucleoF439-ASW** (example application).
5. Connect the board via ST-Link USB and flash using *Run ? Run* in STM32CubeIDE.

> **Note:** Flash the BSW to `0x08000000`.  The ASW raw binary (without the
> STM32CubeIDE debug header) must be signed and placed in SLOT_A (`0x08020000`)
> using the uploader or STM32CubeProgrammer.

---

## Uploader GUI

The Python GUI signs an application binary and uploads it to SLOT_B over UART,
then triggers a swap and/or boot from the board's main menu.

```powershell
cd uploader
pip install -r requirements.txt
python main.py
```

Select the serial port, baud rate (115 200), private key file, and target binary.
Supported key formats:

| Extension | Algorithm |
|-----------|-----------|
| `.pem`    | ECDSA-P256 |
| `.bin`    | ML-DSA-65  |

### Convert a public key to a C byte array

Embed a public key into firmware by generating a C array:

```powershell
python pem_to_c_array.py <key_file> [array_name]
```

Supported input formats: `.pem` (ECDSA / RSA SubjectPublicKeyInfo), `.der`, `.bin` (ML-DSA / LMS raw).

---

## Host Benchmark Tool

Signs a raw image with multiple algorithms and prints key-generation, signing,
and verification timings as a summary table.

> **Required:** The benchmark tool links directly against the **wolfSSL/wolfCrypt C library**.
> The library **must** be installed system-wide (or pointed to via `WOLFSSL_DIR`) with all
> relevant algorithm families enabled.  Without it the build will fail.

```bash
cd benchmark_tool

# Build and install wolfSSL with all required algorithm families (one-time):
cd /path/to/wolfssl
./configure --enable-ecc --enable-rsapss --enable-keygen \
            --enable-dilithium --enable-lms
make && sudo make install

# Build and run the benchmark tool:
cd /path/to/benchmark_tool
make
./benchmark_tool --image images/image.bin
```

| Option | Description |
|--------|-------------|
| `--image <path>` | Raw binary to sign (default: `images/image.bin`) |
| `--version <n>` | Image version written into the header (default: 1) |
| `--force-keygen` | Regenerate all key pairs even if `keys/` already exists |
| `--algo <name>` | Run only the named algorithm; repeatable |

Algorithm names: `ECDSA-P256`, `RSA-2048-PSS`, `RSA-3072-PSS`, `ML-DSA-44`, `ML-DSA-65`, `LMS-SHA256-H5-W8`.

See `benchmark_tool/README.md` for the full option reference.

---

## E2E Test Suite

Hardware-in-the-loop tests using pytest, pyserial (UART), and STM32CubeProgrammer
CLI (SWD flash / option-byte access).

### Setup

1. Flash the BSW to the board.
2. Create a `tests/.env` file (or export the variables directly in your shell):

```dotenv
# Required
SERIAL_PORT=COM6
PRIVATE_KEY=../uploader/keys/private.pem   # must match the BSW embedded public key

# Optional (shown with defaults)
KEY_TYPE=ecdsa                             # or: mldsa
SERIAL_BAUDRATE=115200
ACK_TIMEOUT=5.0
STM32CUBEPROG_BIN=C:\Program Files\...\STM32_Programmer_CLI.exe
IMAGE_PAYLOAD_SIZE=256

# Required for boot tests
REAL_ASW_BIN=../example-asw/NucleoF439-ASW.bin
REAL_ASW_VERSION=1
```

3. Install test dependencies:

```powershell
pip install -r tests/requirements.txt
```

4. Run the full suite:

```powershell
pytest tests/ -v
```

### Test Files

| File | What it covers |
|------|----------------|
| `test_boot.py` | Nominal boot: valid image, CRC/signature failures, WRP enforcement, auto-fix reset |
| `test_update.py` | Firmware upload: happy path, version-floor enforcement, WRP checks, rollback counter |
| `test_swap.py` | Image swap: slot switch, rollback counter advance, SLOT_B integrity checks |
| `test_lifecycle.py` | Multi-cycle scenarios: full upgrade cycle, consecutive swaps, rollback window |
| `test_protocol.py` | ECSS protocol robustness: malformed packets, wrong service types, sequence gaps |

See `TEST_SUITE_DESCRIPTION.md` for a full description of every test case and its assertions.

---

## ECSS Upload Protocol

The BSW speaks a simplified ECSS-E-ST-70-41C–inspired protocol over UART at
115 200 baud.  Each packet has a fixed 7-byte header:

```
[0]   version_type_flags   Version(3 b) | Type(1 b) | Reserved(4 b)
[1]   service_type         0x01 START_UPLOAD  0x02 DATA_CHUNK  0x03 END_UPLOAD
                           0x04 DEBUG_LOG     0x06 ACK         0x15 NACK
[2-3] sequence_count       Big-endian 16-bit counter
[4-5] data_length          Big-endian payload byte count
[6]   header_checksum      XOR of bytes [0..5]
```

See `ECSS_PROTOCOL.md` for the full upload sequence, NACK error-code table, and
timing requirements.

---

## Code Style

All C files use the shared `.clang-format` at the repository root
(Microsoft base style, 4-space indent, `PointerAlignment: Left`, 100-column limit,
`SortIncludes: false` to preserve STM32 HAL include order).

Format-on-save is configured in `.vscode/settings.json` for VS Code users.
All source files include Doxygen-style module and function documentation.
