# benchmark_tool

Host-side signing tool for the NucleoF439 digital-signature benchmark.

It reads a raw application binary, signs it with one or more algorithms,
and writes a signed image file for each one. Results (key-generation,
signing, and verification times) are printed as a summary table.

---

## Build

Requires a wolfSSL installation built with the relevant algorithm support.
Set `WOLFSSL_DIR` to your wolfSSL prefix if it is not installed system-wide.

```bash
make
# or
make WOLFSSL_DIR=/path/to/wolfssl
```

Required wolfSSL features (pass to `./configure`):

```bash
./configure --enable-ecc --enable-rsapss --enable-keygen \
            --enable-dilithium --enable-lms
```

---

## Directory layout

```
benchmark_tool/
├── images/          # input image.bin goes here; signed outputs written here too
├── keys/            # generated key pairs are stored here (auto-created)
└── benchmark_tool   # compiled executable
```

---

## Usage

```
./benchmark_tool [options]
```

### Options

| Option | Description |
|---|---|
| `--image <path>` | Raw application binary to sign (default: `images/image.bin`) |
| `--version <n>` | `imageVersion` field written into the image header (default: `1`) |
| `--force-keygen` | Regenerate all key pairs even if `keys/` already contains them |
| `--algo <name>` | Run only the named algorithm; can be repeated for multiple |
| `--help` / `-h` | Print usage and exit |

### Algorithm names (for `--algo`)

| Name | Description | Sig size |
|---|---|---|
| `ECDSA-P256` | ECDSA with P-256 + SHA-256 | ~72 B |
| `RSA-2048-PSS` | RSA-2048 PSS + SHA-256 | 256 B |
| `RSA-3072-PSS` | RSA-3072 PSS + SHA-256 | 384 B |
| `ML-DSA-44` | ML-DSA (Dilithium) level 2 | 2420 B |
| `ML-DSA-65` | ML-DSA (Dilithium) level 3 | 3309 B |
| `LMS-SHA256-H5-W8` | LMS-SHA256-M32-H5 / LMOTS-N32-W8 | ~1292 B |

---

## Examples

Run all algorithms on the default image:

```bash
./benchmark_tool
```

Run only RSA-2048 and RSA-3072:

```bash
./benchmark_tool --algo RSA-2048-PSS --algo RSA-3072-PSS
```

Use a custom image and force fresh keys:

```bash
./benchmark_tool --image images/my_app.bin --version 3 --force-keygen
```

---

## Key management

Keys are generated on the first run and saved in `keys/` as DER (RSA, ECDSA)
or raw binary (ML-DSA, LMS) files. Subsequent runs reuse them automatically.

Use `--force-keygen` to regenerate. After generating new keys, the matching
public key must be pasted into the corresponding `sig_*.c` file in
`STM32CubeIDE/NucleoF439-Benchmark/Core/Src/` before flashing the target.
Use `pem_to_c_array.py` in the `uploader/` directory to convert a public key
file to a C byte array.
