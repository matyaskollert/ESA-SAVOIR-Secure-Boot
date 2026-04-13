/*
 * binary_processor.c — Firmware image assembly (C port of Python binary_processor.py).
 */

#include "binary_processor.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

static uint32_t crc32_compute(const uint8_t* buf, size_t len)
{
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t byte_index = 0; byte_index < len; ++byte_index) {
        crc ^= buf[byte_index];
        for (int bit_index = 0; bit_index < 8; ++bit_index)
            crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc & 1u)));
    }
    return crc ^ 0xFFFFFFFFu;
}

// Write a little-endian 16-bit value into buf.
static void write_le16(uint8_t* buf, uint16_t v)
{
    buf[0] = (uint8_t)(v & 0xFFu);
    buf[1] = (uint8_t)((v >> 8u) & 0xFFu);
}

// Write a little-endian 32-bit value into buf.
static void write_le32(uint8_t* buf, uint32_t v)
{
    buf[0] = (uint8_t)(v & 0xFFu);
    buf[1] = (uint8_t)((v >> 8u) & 0xFFu);
    buf[2] = (uint8_t)((v >> 16u) & 0xFFu);
    buf[3] = (uint8_t)((v >> 24u) & 0xFFu);
}

size_t make_sign_region(const uint8_t* image_data, size_t image_size,
                        uint16_t image_version,
                        uint8_t* out_buf, size_t out_buf_capacity)
{
    /*
     * Layout (matches Python make_sign_region):
     *   magic(2) + version(2) + imageSize(4) + zeros(SIGNATURE_FIELD+PADDING_SIZE) + image_data
     */
    size_t sign_len = (size_t)HEADER_FIXED - 4u   // magic+version+size = 8 bytes
                    + SIGNATURE_FIELD + PADDING_SIZE
                    + image_size;
    // HEADER_FIXED-4 = 8 bytes for magic+version+size
    sign_len = 8u + (size_t)SIGNATURE_FIELD + (size_t)PADDING_SIZE + image_size;

    if (out_buf_capacity < sign_len) return 0;

    uint8_t* write_ptr = out_buf;

    write_le16(write_ptr, (uint16_t)IMAGE_MAGIC);   write_ptr += 2;
    write_le16(write_ptr, image_version);           write_ptr += 2;
    write_le32(write_ptr, (uint32_t)image_size);    write_ptr += 4;

    memset(write_ptr, 0, (size_t)SIGNATURE_FIELD + (size_t)PADDING_SIZE);
    write_ptr += (size_t)SIGNATURE_FIELD + (size_t)PADDING_SIZE;

    memcpy(write_ptr, image_data, image_size);

    return sign_len;
}

int build_signed_image(const uint8_t* image_data, size_t image_size,
                       const sig_algo_t* algo, sig_ctx_t* ctx,
                       const char* out_path, uint16_t image_version,
                       uint8_t** raw_sig_out, size_t* raw_sig_len_out,
                       uint8_t** sign_region_out, size_t* sign_region_len_out)
{
    int ret = -1;
    uint8_t* sign_reg = NULL;
    uint8_t* sig_buf = NULL;
    uint8_t* full_image = NULL;
    size_t sign_len = 0;
    size_t sig_written = 0;

    sign_len = 8u + (size_t)SIGNATURE_FIELD + (size_t)PADDING_SIZE + image_size;
    sign_reg = (uint8_t*)malloc(sign_len);
    if (!sign_reg)
    {
        fprintf(stderr, "OOM: sign_reg\n");
        goto cleanup;
    }

    if (make_sign_region(image_data, image_size, image_version,
                         sign_reg, sign_len) != sign_len) {
        fprintf(stderr, "make_sign_region failed\n");
        goto cleanup;
    }

    sig_buf = (uint8_t*)malloc((size_t)algo->sig_len + 256u); // small headroom
    if (!sig_buf)
    {
        fprintf(stderr, "OOM: sig_buf\n");
        goto cleanup;
    }

    if (algo->sign(ctx, sign_reg, sign_len, sig_buf, &sig_written) != 0)
    {
        fprintf(stderr, "  [ERROR] Signing failed.\n");
        goto cleanup;
    }

    if (sig_written > (size_t)SIGNATURE_FIELD) {
        fprintf(stderr,
            "  [ERROR] %s signature is %zu B, exceeds the %u-byte "
            "SIGNATURE_FIELD in image_header_t.\n"
            "          Enlarge signature[] to at least %zu bytes and recompile.\n",
            algo->name, sig_written, SIGNATURE_FIELD, sig_written);
        goto cleanup;
    }
    printf("    Signature   : %zu bytes\n", sig_written);

    /* ── 3. Assemble header body ────────────────────────────────────── *
     * header_body = magic(2)+version(2)+size(4) + sig_padded(4096) + padding(1012)
     * = IMAGE_OFFSET - 4 bytes (CRC not included yet)                       */
    size_t header_body_len = (size_t)IMAGE_OFFSET - 4u;
    full_image = (uint8_t*)calloc(1, (size_t)IMAGE_OFFSET + image_size);
    if (!full_image)
    {
        fprintf(stderr, "OOM: full_image\n");
        goto cleanup;
    }

    uint8_t* hb = full_image + 4u; // leave 4 bytes at front for CRC
    write_le16(hb,     (uint16_t)IMAGE_MAGIC);
    write_le16(hb + 2, image_version);
    write_le32(hb + 4, (uint32_t)image_size);
    // sig field: copy sig_written bytes, rest already zero from calloc
    memcpy(hb + 8u, sig_buf, sig_written);
    // padding already zero
    memcpy(full_image + (size_t)IMAGE_OFFSET, image_data, image_size);

    /* ── 4. Compute CRC-32 ───────────────────────────────────────────── *
     * Covers header_body (IMAGE_OFFSET - 4 bytes) + image_data.
     * Matches Python: binascii.crc32(header_body + image_data)              */
    {
        const uint8_t* crc_start = full_image + 4u;
        size_t crc_len = header_body_len + image_size;
        uint32_t crc = crc32_compute(crc_start, crc_len);
        write_le32(full_image, crc);
        printf("    CRC-32      : 0x%08X\n", crc);
    }

    {
        FILE* output_file = fopen(out_path, "wb");
        if (!output_file)
        {
            perror(out_path);
            goto cleanup;
        }
        size_t total = (size_t)IMAGE_OFFSET + image_size;
        if (fwrite(full_image, 1, total, output_file) != total)
        {
            fclose(output_file);
            fprintf(stderr, "  [ERROR] Short write to %s\n", out_path);
            goto cleanup;
        }
        fclose(output_file);

        // Extract just the filename from out_path for the print
        const char* filename = out_path;
        for (const char* path_ptr = out_path; *path_ptr; ++path_ptr)
            if (*path_ptr == '/' || *path_ptr == '\\') filename = path_ptr + 1;

        printf("    Written     : %s  (%zu bytes)\n",
               filename, (size_t)IMAGE_OFFSET + image_size);
    }

    if (raw_sig_out) {
        *raw_sig_out = sig_buf;
        sig_buf = NULL;   // transfer ownership
    }
    if (raw_sig_len_out) *raw_sig_len_out = sig_written;
    if (sign_region_out) {
        *sign_region_out = sign_reg;
        sign_reg = NULL;   // transfer ownership
    }
    if (sign_region_len_out) *sign_region_len_out = sign_len;

    ret = 0;

cleanup:
    free(sign_reg);
    free(sig_buf);
    free(full_image);
    return ret;
}
