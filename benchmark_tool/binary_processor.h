/*
 * binary_processor.h — Firmware image assembly for the host benchmark tool.
 *
 * Image layout (matches NucleoF439-BSW image.h and the Python binary_processor.py):
 *
 *   Offset   Size    Field
 *   ──────── ─────── ──────────────────────────────────────────────────────
 *   0x0000      4    CRC-32 (covers bytes 0x04 .. IMAGE_OFFSET-1 + image_data)
 *   0x0004      2    imageMagic  (0xABCD)
 *   0x0006      2    imageVersion
 *   0x0008      4    imageSize   (byte count of the raw application binary)
 *   0x000C   4096    signature   (raw bytes, zero-padded to SIGNATURE_FIELD)
 *   0x100C   1012    padding     (zeroes)
 *   ─────────────────────────────────────────────────────────────────────
 *   0x1400    n      image_data  (raw application binary)
 *
 *   IMAGE_OFFSET     = 0x1400 = 5120 bytes
 *   SIGNATURE_FIELD  = 4096 bytes
 *
 * Signing region (bytes 0x04 .. IMAGE_OFFSET + imageSize - 1, sig zeroed):
 *   imageMagic(2) + imageVersion(2) + imageSize(4) + zeros(5108) + image_data
 */

#ifndef BENCHMARK_BINARY_PROCESSOR_H
#define BENCHMARK_BINARY_PROCESSOR_H

#include <stdint.h>
#include <stddef.h>
#include "sig_algo.h"

#ifdef __cplusplus
extern "C" {
#endif

#define IMAGE_MAGIC       0xABCDU
#define IMAGE_OFFSET      0x1400U       // 5120 bytes — total header region
#define SIGNATURE_FIELD   4096U         // bytes reserved for the signature
#define HEADER_FIXED      12U           // CRC(4)+magic(2)+version(2)+size(4)
#define PADDING_SIZE      (IMAGE_OFFSET - HEADER_FIXED - SIGNATURE_FIELD) // 1012

/*
 * Build the signing region into *out_buf (caller-allocated, must be at least
 * IMAGE_OFFSET - 4 + image_size bytes).
 *
 * Matches Python make_sign_region():
 *   header_part = struct.pack("<HHI", magic, version, image_size)
 *   zeros       = b'\x00' * (SIGNATURE_FIELD + PADDING_SIZE)
 *   return header_part + zeros + image_data
 *
 * Returns the total number of bytes written into out_buf.
 */
size_t make_sign_region(const uint8_t* image_data, size_t image_size,
                        uint16_t image_version,
                        uint8_t* out_buf, size_t out_buf_capacity);

/*
 * Sign image_data, assemble the full firmware image, and write it to out_path.
 *
 * @param image_data      Raw application binary bytes.
 * @param image_size      Length of image_data in bytes.
 * @param algo            Pointer to the algorithm descriptor.
 * @param ctx             Algorithm context with private key loaded.
 * @param out_path        Destination file path for the signed image.
 * @param image_version   Value written to imageVersion in the header.
 * @param raw_sig_out     If non-NULL, set to a malloc'd buffer containing the
 *                        raw signature bytes (caller must free).
 * @param raw_sig_len_out If non-NULL, set to the size of raw_sig_out.
 * @param sign_region_out If non-NULL, set to a malloc'd copy of the region
 *                        that was signed (caller must free).
 * @param sign_region_len_out If non-NULL, set to the length of sign_region_out.
 * @return 0 on success, negative on error.
 */
int build_signed_image(const uint8_t* image_data, size_t image_size,
                       const sig_algo_t* algo, sig_ctx_t* ctx,
                       const char* out_path, uint16_t image_version,
                       uint8_t** raw_sig_out, size_t* raw_sig_len_out,
                       uint8_t** sign_region_out, size_t* sign_region_len_out);

#ifdef __cplusplus
}
#endif

#endif /* BENCHMARK_BINARY_PROCESSOR_H */
