/*
 * benchmark.c
 *
 * Loads the MAIN image from SLOT_A_FLASH_ADDRESS into RAM (mimicking
 * imageLoad() from image.c but without launching the image), zeroes the
 * signature field as the signer did, then runs the signature verification
 * algorithm BENCHMARK_ITERATIONS times and prints timing results.
 */

#include "benchmark.h"
#include "sig_algo.h"
#include "image.h"
#include "flash.h"
#include <string.h>
#include <stdio.h>
#include "stm32f4xx_hal.h"

void benchmarkRun(void)
{
    const image_header_t* header = (const image_header_t*)SLOT_A_FLASH_ADDRESS;

    if (header->imageMagic != IMAGE_MAGIC)
    {
        printf("benchmarkRun: no valid image at 0x%08lX (magic=0x%04X)\r\n",
               (uint32_t)SLOT_A_FLASH_ADDRESS, header->imageMagic);
        return;
    }

    uint32_t copySize = IMAGE_OFFSET + header->imageSize;

    printf("\r\n");
    printf("=========================================\r\n");
    printf("  Digital Signature Benchmark\r\n");
    printf("  Algorithm  : %s\r\n", g_algo.name);
    printf("  Image size : %lu bytes\r\n", header->imageSize);
    printf("  Sig field  : %lu bytes\r\n", g_algo.sig_len);
    printf("  Iterations : %d\r\n", BENCHMARK_ITERATIONS);
    printf("=========================================\r\n");

    void* ramDst = (void*)BOOT_RAM_ADDRESS;
    memcpy(ramDst, (const void*)SLOT_A_FLASH_ADDRESS, copySize);

    // Signed region: [CRC excluded] imageMagic..imageSize..sig=0..padding..code
    // IMAGE_HEADER_DS_OFFSET skips the leading CRC (4 B), magic (2 B),
    // version (2 B), imageSize (4 B)  →  12 bytes total.
    memset((uint8_t*)ramDst + IMAGE_HEADER_DS_OFFSET, 0,
           IMAGE_OFFSET - IMAGE_HEADER_DS_OFFSET);

    // Pointers for the verify call use the same convention as imageVerify in image.c.
    const byte* msg = (const byte*)BOOT_RAM_ADDRESS + 4; // skip CRC
    uint32_t msgLen = IMAGE_OFFSET + header->imageSize - 4;
    const byte* sig = header->signature;                  // from flash
    uint32_t sigLen = g_algo.sig_len;

    if (g_algo.init() != 0)
    {
        printf("benchmarkRun: key init failed\r\n");
        return;
    }

    uint32_t totalMs = 0;

    for (int i = 0; i < BENCHMARK_ITERATIONS; i++)
    {
        uint32_t t0 = HAL_GetTick();
        int16_t result = g_algo.verify(msg, msgLen, sig, sigLen);
        uint32_t elapsed = HAL_GetTick() - t0;
        totalMs += elapsed;

        printf("  [%d/%d]  %-5s  %lu ms\r\n",
               i + 1, BENCHMARK_ITERATIONS,
               (result == 1) ? "PASS" : "FAIL",
               elapsed);
    }

    printf("-----------------------------------------\r\n");
    printf("  Average    : %lu ms\r\n", totalMs / (uint32_t)BENCHMARK_ITERATIONS);
    printf("=========================================\r\n\r\n");

    g_algo.cleanup();
}
