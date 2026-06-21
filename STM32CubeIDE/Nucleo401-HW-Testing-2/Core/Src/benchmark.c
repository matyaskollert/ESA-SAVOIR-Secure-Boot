/*
 * benchmark.c
 *
 * Loads the BOOT image from BOOT_FLASH_ADDRESS into RAM (mimicking
 * imageLoad() from image.c but without launching the image), zeroes the
 * signature field as the signer did, then runs the signature verification
 * algorithm BENCHMARK_ITERATIONS times and prints timing results.
 */

#include "benchmark.h"
#include "sig_algo.h"
#include "image.h"
#include <string.h>
#include <stdio.h>
#include "stm32f4xx_hal.h"

void benchmarkRun(void)
{
    const image_header_t *header = (const image_header_t *)BOOT_FLASH_ADDRESS;

    if (header->imageMagic != IMAGE_MAGIC)
    {
        printf("benchmarkRun: no valid image at 0x%08lX (magic=0x%04X)\r\n",
               (uint32_t)BOOT_FLASH_ADDRESS, header->imageMagic);
        return;
    }

    uint32_t copySize = IMAGE_OFFSET + header->imageSize;

    // printf("\r\n");
    // printf("=========================================\r\n");
    // printf("  Digital Signature Benchmark\r\n");
    // printf("  Algorithm  : %s\r\n", g_algo.name);
    // printf("  Image size : %lu bytes\r\n", header->imageSize);
    // printf("  Sig field  : %lu bytes\r\n", g_algo.sig_len);
    // printf("=========================================\r\n");

    void *ramDst = (void *)BOOT_RAM_ADDRESS;
    memcpy(ramDst, (const void *)BOOT_FLASH_ADDRESS, copySize);

    // Signed region: [CRC excluded] imageMagic..imageSize..sig=0..padding..code
    // IMAGE_HEADER_DS_OFFSET skips the leading CRC (4 B), magic (2 B),
    // version (2 B), imageSize (4 B)  →  12 bytes total.
    memset((uint8_t *)ramDst + IMAGE_HEADER_DS_OFFSET, 0,
           IMAGE_OFFSET - IMAGE_HEADER_DS_OFFSET);

    // Pointers for the verify call use the same convention as imageVerify in image.c.
    const byte *msg = (const byte *)BOOT_RAM_ADDRESS + 4; // skip CRC
    uint32_t msgLen = IMAGE_OFFSET + header->imageSize - 4;
    const byte *sig = header->signature; // from flash
    uint32_t sigLen = g_algo.sig_len;

    if (g_algo.init() != 0)
    {
        printf("benchmarkRun: key init failed\r\n");
        return;
    }

    int16_t result = g_algo.verify(msg, msgLen, sig, sigLen);
    printf("%-5s\r\n", (result == 1) ? "PASS" : "FAIL");

    g_algo.cleanup();
}
