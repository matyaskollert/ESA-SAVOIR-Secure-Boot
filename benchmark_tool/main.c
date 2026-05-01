/*
 * main.c — Digital Signature Signing Benchmark (C port of run_benchmark.py)
 *
 * Reads an application binary, signs it with every supported algorithm,
 * writes image_<ALGO>.bin for each one, and prints a timing summary.
 *
 * Usage:
 *   ./benchmark_tool [options]
 *
 * Options:
 *   --image <path>      Path to the raw application binary (default: images/image.bin)
 *   --version <n>       imageVersion field in the header (default: 1)
 *   --force-keygen      Regenerate all key pairs even if keys/ exists
 *   --algo <name>       Run only the named algorithm (may be repeated)
 *                       Names: ECDSA-P256, RSA-3072-PSS, RSA-4096-PSS,
 *                              ML-DSA-44, ML-DSA-65,
 *                              LMS-SHA256-H5-W8
 *
 * Output files are written in the same directory as the input image.
 * Keys are persisted in keys/ next to the binary for reuse.
 *
 * Algorithm availability depends on wolfSSL compile flags:
 *   ECDSA, RSA  : HAVE_ECC, WC_RSA_PSS (wolfSSL defaults)
 *   ML-DSA      : HAVE_DILITHIUM, WOLFSSL_WC_DILITHIUM
 *   LMS         : WOLFSSL_HAVE_LMS
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>

#include <sys/stat.h>
#include <sys/types.h>
#define PATH_SEP '/'

#include "binary_processor.h"
#include "sig_algo.h"
#include "sig_ecdsa.h"
#include "sig_rsa.h"
#include "sig_mldsa.h"
#include "sig_lms.h"

static double now_sec()
{
    return (double)clock() / CLOCKS_PER_SEC;
}

#define MAX_NAME 32

typedef struct {
    char name[MAX_NAME];
    double keygen_s;    // -1 = keys were loaded (not generated)
    double sign_s;
    double verify_s;
    int status;      // 0=OK, 1=skip/unavailable, 2=error
    char status_msg[128];
} result_t;

static int file_exists(const char* path)
{
    FILE* file_handle = fopen(path, "rb");
    if (!file_handle)
        return 0;
    fclose(file_handle);
    return 1;
}

static uint8_t* read_entire_file(const char* path, size_t* len_out)
{
    FILE* file_handle = fopen(path, "rb");
    if (!file_handle)
    {
        perror(path);
        return NULL;
    }
    fseek(file_handle, 0, SEEK_END);
    long file_size = ftell(file_handle);
    rewind(file_handle);
    if (file_size <= 0)
    {
        fclose(file_handle);
        return NULL;
    }
    uint8_t* file_buffer = (uint8_t*)malloc((size_t)file_size);
    if (!file_buffer)
    {
        fclose(file_handle);
        return NULL;
    }
    if (fread(file_buffer, 1, (size_t)file_size, file_handle) != (size_t)file_size)
    {
        free(file_buffer);
        fclose(file_handle);
        return NULL;
    }
    *len_out = (size_t)file_size;
    fclose(file_handle);
    return file_buffer;
}

// Build "dir/filename" into out_buf (max out_len bytes).
static void join_path(char* out_buf, size_t out_len,
                      const char* dir, const char* filename)
{
    snprintf(out_buf, out_len, "%s%c%s", dir, PATH_SEP, filename);
}

// Replace '/' and ' ' with '_' in place.
static void safe_name(char* name_text)
{
    for (; *name_text; ++name_text)
        if (*name_text == '/' || *name_text == ' ')
            *name_text = '_';
}

static result_t run_one(const sig_algo_t* algo,
                        const uint8_t* image_data, size_t image_size,
                        const char* keys_dir, const char* out_dir,
                        uint16_t image_version, int force_keygen)
{
    result_t r;
    memset(&r, 0, sizeof(r));
    strncpy(r.name, algo->name, MAX_NAME - 1);
    r.keygen_s = -1.0;
    r.sign_s = -1.0;
    r.verify_s = -1.0;
    r.status   = 2;

    // Build key file paths
    char safe[MAX_NAME];
    strncpy(safe, algo->name, MAX_NAME - 1);
    safe_name(safe);

    char priv_path[640], pub_path[640];
    snprintf(priv_path, sizeof(priv_path), "%s%c%s_private%s",
             keys_dir, PATH_SEP, safe, algo->key_extension);
    snprintf(pub_path, sizeof(pub_path), "%s%c%s_public%s",
             keys_dir, PATH_SEP, safe, algo->key_extension);

    printf("\n--- %s ", algo->name);
    for (int dash_index = (int)strlen(algo->name); dash_index < 52; ++dash_index)
        putchar('-');
    printf("\n");

    // Allocate context
    sig_ctx_t* ctx = algo->alloc();
    if (!ctx)
    {
        fprintf(stderr, "  [ERROR] alloc() failed\n");
        snprintf(r.status_msg, sizeof(r.status_msg), "ALLOC ERROR");
        return r;
    }

    int keys_exist = file_exists(priv_path) && file_exists(pub_path);

    if (force_keygen || !keys_exist)
    {
        printf("  Generating key pair ...\n");
        double start_time = now_sec();
        int ret = algo->generate_keys(ctx, priv_path, pub_path);
        r.keygen_s = now_sec() - start_time;
        if (ret != 0)
        {
            fprintf(stderr, "  [ERROR] Key generation failed: %d\n", ret);
            snprintf(r.status_msg, sizeof(r.status_msg), "KEYGEN ERROR: %d", ret);
            algo->free_ctx(ctx);
            return r;
        }
        printf("  Key generation : %.1f ms\n", r.keygen_s * 1000.0);
    }
    else
    {
        printf("  Loading existing keys ...\n");
        int ret = algo->load_keys(ctx, priv_path, pub_path);
        if (ret != 0)
        {
            fprintf(stderr, "  [ERROR] Key load failed: %d\n", ret);
            snprintf(r.status_msg, sizeof(r.status_msg), "KEY LOAD ERROR: %d", ret);
            algo->free_ctx(ctx);
            return r;
        }
    }

    char out_name[MAX_NAME + 32];
    char out_safe[MAX_NAME];
    strncpy(out_safe, algo->name, MAX_NAME - 1);
    safe_name(out_safe);
    snprintf(out_name, sizeof(out_name), "image_%s.bin", out_safe);

    char out_path[640];
    snprintf(out_path, sizeof(out_path), "%s%c%s", out_dir, PATH_SEP, out_name);

    printf("  Signing -> %s ...\n", out_name);

    uint8_t* raw_sig = NULL;
    uint8_t* sign_region = NULL;
    size_t raw_sig_len = 0;
    size_t sign_reg_len = 0;

    double start_time = now_sec();
    int ret = build_signed_image(image_data, image_size, algo, ctx,
                                 out_path, image_version,
                                 &raw_sig, &raw_sig_len,
                                 &sign_region, &sign_reg_len);
    r.sign_s = now_sec() - start_time;

    if (ret != 0)
    {
        snprintf(r.status_msg, sizeof(r.status_msg), "SIGN ERROR: %d", ret);
        free(raw_sig);
        free(sign_region);
        algo->free_ctx(ctx);
        return r;
    }

    printf("  Verifying ... ");
    fflush(stdout);

    start_time = now_sec();
    int ok = algo->verify(ctx, sign_region, sign_reg_len,
                          raw_sig, raw_sig_len);
    r.verify_s = now_sec() - start_time;

    printf("%s\n", (ok == 1) ? "PASS" : "FAIL");
    printf("  Sign : %.1f ms  |  Verify : %.1f ms\n",
           r.sign_s * 1000.0, r.verify_s * 1000.0);

    r.status = (ok == 1) ? 0 : 2;
    if (r.status == 0)
        strncpy(r.status_msg, "OK", sizeof(r.status_msg) - 1);
    else
        strncpy(r.status_msg, "VERIFY FAILED", sizeof(r.status_msg) - 1);

    free(raw_sig);
    free(sign_region);
    algo->free_ctx(ctx);
    return r;
}

static void print_summary(const result_t* results, int result_count)
{
#define W_ALGO    22
#define W_KEYGEN  12
#define W_SIGN    12
#define W_VERIFY  12

    int total_w = W_ALGO + W_KEYGEN + W_SIGN + W_VERIFY + 2 + 12;

    printf("\n");
    for (int column_index = 0; column_index < total_w; ++column_index) putchar('=');
    printf("\n  BENCHMARK SUMMARY\n");
    for (int column_index = 0; column_index < total_w; ++column_index) putchar('=');
    printf("\n");

    printf("%-*s%*s%*s%*s  %s\n",
           W_ALGO,   "Algorithm",
           W_KEYGEN, "KeyGen(ms)",
           W_SIGN,   "Sign(ms)",
           W_VERIFY, "Verify(ms)",
           "Status");

    for (int column_index = 0; column_index < total_w; ++column_index) putchar('-');
    printf("\n");

    for (int row_index = 0; row_index < result_count; ++row_index) {
        const result_t* result = &results[row_index];

        char keygen_s[16], sign_s[16], verify_s[16];
        if (result->keygen_s < 0)
            snprintf(keygen_s, sizeof(keygen_s), "%*s", W_KEYGEN, "n/a");
        else
            snprintf(keygen_s, sizeof(keygen_s), "%*.1f", W_KEYGEN,
                     result->keygen_s * 1000.0);

        if (result->sign_s < 0)
            snprintf(sign_s, sizeof(sign_s), "%*s", W_SIGN, "n/a");
        else
            snprintf(sign_s, sizeof(sign_s), "%*.1f", W_SIGN,
                     result->sign_s * 1000.0);

        if (result->verify_s < 0)
            snprintf(verify_s, sizeof(verify_s), "%*s", W_VERIFY, "n/a");
        else
            snprintf(verify_s, sizeof(verify_s), "%*.1f", W_VERIFY,
                     result->verify_s * 1000.0);

        printf("%-*s%s%s%s  %s\n",
               W_ALGO, result->name,
               keygen_s, sign_s, verify_s,
               result->status_msg);
    }

    for (int column_index = 0; column_index < total_w; ++column_index) putchar('=');
    printf("\n");
}

typedef struct {
    const sig_algo_t* algo;
    int enabled;
} algo_entry_t;

// Build the registry at startup — RSA and ML-DSA variants obtained via sig_*_get().
static algo_entry_t s_registry[9];
static int s_registry_n = 0;

/* -------------------------------------------------------------------------
 * Random-payload benchmark
 * ------------------------------------------------------------------------- */

#define N_RAND_SIZES 2
static const size_t    RAND_SIZES[N_RAND_SIZES]  = { 1UL*1024, 128UL*1024 };
static const char*     RAND_LABELS[N_RAND_SIZES] = { "1kB", "128kB" };

typedef struct {
    char   algo_name[MAX_NAME];
    char   size_label[8];
    double sign_s;
    double verify_s;
    int    status;   // 0=OK, 2=error
} rand_result_t;

static void print_random_summary(const rand_result_t* rr, int n)
{
#define RW_ALGO   22
#define RW_SIZE    8
#define RW_SIGN   12
#define RW_VFY    12
    int total_w = RW_ALGO + RW_SIZE + RW_SIGN + RW_VFY + 2 + 10;

    printf("\n");
    for (int i = 0; i < total_w; ++i) putchar('=');
    printf("\n  RANDOM PAYLOAD BENCHMARK SUMMARY\n");
    for (int i = 0; i < total_w; ++i) putchar('=');
    printf("\n");
    printf("%-*s%-*s%*s%*s  %s\n",
           RW_ALGO, "Algorithm", RW_SIZE, "Size",
           RW_SIGN, "Sign(ms)", RW_VFY, "Verify(ms)", "Status");
    for (int i = 0; i < total_w; ++i) putchar('-');
    printf("\n");

    for (int i = 0; i < n; ++i) {
        char sign_buf[16], vfy_buf[16];
        if (rr[i].sign_s < 0)
            snprintf(sign_buf, sizeof(sign_buf), "%*s", RW_SIGN, "n/a");
        else
            snprintf(sign_buf, sizeof(sign_buf), "%*.1f", RW_SIGN, rr[i].sign_s * 1000.0);
        if (rr[i].verify_s < 0)
            snprintf(vfy_buf, sizeof(vfy_buf), "%*s", RW_VFY, "n/a");
        else
            snprintf(vfy_buf, sizeof(vfy_buf), "%*.1f", RW_VFY, rr[i].verify_s * 1000.0);

        printf("%-*s%-*s%s%s  %s\n",
               RW_ALGO, rr[i].algo_name,
               RW_SIZE, rr[i].size_label,
               sign_buf, vfy_buf,
               (rr[i].status == 0) ? "OK" : "ERROR");
    }
    for (int i = 0; i < total_w; ++i) putchar('=');
    printf("\n");
}

static int run_random_benchmarks(int image_version,
                                 const char* keys_dir,
                                 const char* out_dir,
                                 rand_result_t* rr_out, int* n_out)
{
    *n_out = 0;

    /* seed stdlib RNG — used only for innocuous payload data, not key material */
    srand((unsigned)time(NULL));

    printf("\n");
    for (int i = 0; i < 67; ++i) putchar('=');
    printf("\n  Random Payload Signing Benchmark\n");
    for (int i = 0; i < 67; ++i) putchar('-');
    printf("\n  Sizes: 1 kB, 128 kB\n");
    for (int i = 0; i < 67; ++i) putchar('=');
    printf("\n");

    for (int entry_index = 0; entry_index < s_registry_n; ++entry_index) {
        if (!s_registry[entry_index].enabled) continue;
        if (!s_registry[entry_index].algo)    continue;

        const sig_algo_t* algo = s_registry[entry_index].algo;

        char safe[MAX_NAME];
        strncpy(safe, algo->name, MAX_NAME - 1);
        safe[MAX_NAME - 1] = '\0';
        safe_name(safe);

        char priv_path[640], pub_path[640];
        snprintf(priv_path, sizeof(priv_path), "%s%c%s_private%s",
                 keys_dir, PATH_SEP, safe, algo->key_extension);
        snprintf(pub_path, sizeof(pub_path), "%s%c%s_public%s",
                 keys_dir, PATH_SEP, safe, algo->key_extension);

        printf("\n--- %s ", algo->name);
        for (int d = (int)strlen(algo->name); d < 52; ++d) putchar('-');
        printf("\n");

        sig_ctx_t* ctx = algo->alloc();
        if (!ctx) {
            fprintf(stderr, "  [ERROR] alloc() failed\n");
            continue;
        }
        if (algo->load_keys(ctx, priv_path, pub_path) != 0) {
            fprintf(stderr, "  [ERROR] Key load failed\n");
            algo->free_ctx(ctx);
            continue;
        }

        for (int s = 0; s < N_RAND_SIZES; ++s) {
            size_t      sz    = RAND_SIZES[s];
            const char* label = RAND_LABELS[s];

            rand_result_t* rr = &rr_out[(*n_out)++];
            memset(rr, 0, sizeof(*rr));
            strncpy(rr->algo_name,  algo->name, MAX_NAME - 1);
            strncpy(rr->size_label, label,      sizeof(rr->size_label) - 1);
            rr->sign_s = rr->verify_s = -1.0;
            rr->status = 2;

            uint8_t* rdata = (uint8_t*)malloc(sz);
            if (!rdata) {
                fprintf(stderr, "  [%s] malloc(%zu) failed\n", label, sz);
                continue;
            }
            for (size_t b = 0; b < sz; ++b)
                rdata[b] = (uint8_t)(rand() & 0xFF);

            char out_name[MAX_NAME + 32];
            snprintf(out_name, sizeof(out_name), "random_%s_%s.bin", label, safe);
            char out_path[640];
            snprintf(out_path, sizeof(out_path), "%s%c%s", out_dir, PATH_SEP, out_name);

            printf("  [%s] Signing -> %s ...\n", label, out_name);

            uint8_t* raw_sig    = NULL;
            uint8_t* sign_region = NULL;
            size_t   raw_sig_len = 0, sign_reg_len = 0;

            double t0 = now_sec();
            int ret = build_signed_image(rdata, sz, algo, ctx,
                                         out_path, (uint16_t)image_version,
                                         &raw_sig, &raw_sig_len,
                                         &sign_region, &sign_reg_len);
            rr->sign_s = now_sec() - t0;

            if (ret != 0) {
                fprintf(stderr, "  [%s] Sign error: %d\n", label, ret);
                free(rdata);
                continue;
            }

            t0 = now_sec();
            int ok = algo->verify(ctx, sign_region, sign_reg_len, raw_sig, raw_sig_len);
            rr->verify_s = now_sec() - t0;

            printf("  [%s] Sign: %.1f ms  |  Verify: %.1f ms  |  %s\n",
                   label, rr->sign_s * 1000.0, rr->verify_s * 1000.0,
                   (ok == 1) ? "PASS" : "FAIL");
            rr->status = (ok == 1) ? 0 : 2;

            free(raw_sig);
            free(sign_region);
            free(rdata);
        }

        algo->free_ctx(ctx);
    }
    return 0;
}

static void registry_init()
{
    s_registry[s_registry_n++] = (algo_entry_t){ &sig_ecdsa, 1 };
    s_registry[s_registry_n++] = (algo_entry_t){ sig_rsa_get(RSA_3072), 1 };
    s_registry[s_registry_n++] = (algo_entry_t){ sig_rsa_get(RSA_4096), 1 };
    s_registry[s_registry_n++] = (algo_entry_t){ sig_mldsa_get(ML_DSA_44), 1 };
    s_registry[s_registry_n++] = (algo_entry_t){ sig_mldsa_get(ML_DSA_65), 1 };
    s_registry[s_registry_n++] = (algo_entry_t){ &sig_lms, 1 };
}

// Disable all algorithms whose name does not appear in the filter list.
static void registry_filter(const char** names, int count)
{
    for (int entry_index = 0; entry_index < s_registry_n; ++entry_index) {
        int found = 0;
        for (int filter_index = 0; filter_index < count; ++filter_index)
        {
            if (strcmp(s_registry[entry_index].algo->name, names[filter_index]) == 0)
            {
                found = 1;
                break;
            }
        }
        s_registry[entry_index].enabled = found;
    }
}

int main(int argc, char **argv)
{
    const char* image_path = "images/image.bin";
    int image_version = 1;
    int force_keygen = 0;
    const char* filter[8];
    int filter_n = 0;

    for (int arg_index = 1; arg_index < argc; ++arg_index)
    {
        if (strcmp(argv[arg_index], "--image") == 0 && arg_index + 1 < argc)
        {
            image_path = argv[++arg_index];
        }
        else if (strcmp(argv[arg_index], "--version") == 0 && arg_index + 1 < argc)
        {
            image_version = atoi(argv[++arg_index]);
        }
        else if (strcmp(argv[arg_index], "--force-keygen") == 0)
        {
            force_keygen = 1;
        }
        else if (strcmp(argv[arg_index], "--algo") == 0 && arg_index + 1 < argc)
        {
            if (filter_n < 8)
                filter[filter_n++] = argv[++arg_index];
        }
        else if (strcmp(argv[arg_index], "--help") == 0 || strcmp(argv[arg_index], "-h") == 0)
        {
            puts("Usage: benchmark_tool [--image <path>] [--version <n>]");
            puts("                      [--force-keygen] [--algo <name>]...");
            puts("");
            puts("  --image <path>      Raw application binary (default: images/image.bin)");
            puts("  --version <n>       imageVersion field (default: 1)");
            puts("  --force-keygen      Regenerate all key pairs");
            puts("  --algo <name>       Run only this algorithm (repeatable)");
            puts("");
            puts("  Algorithms: ECDSA-P256  RSA-3072-PSS  RSA-4096-PSS");
            puts("              ML-DSA-44  ML-DSA-65");
            puts("              LMS-SHA256-H5-W8");
            puts("");
            puts("  Output files per algorithm:");
            puts("    image_<ALGO>.bin              — signed real image");
            puts("    random_1kB_<ALGO>.bin         — signed 1 kB random payload");
            puts("    random_128kB_<ALGO>.bin       — signed 128 kB random payload");
            return 0;
        }
        else
        {
            fprintf(stderr, "Unknown option: %s\n", argv[arg_index]);
            return 1;
        }
    }

    size_t image_size = 0;
    uint8_t* image_data = read_entire_file(image_path, &image_size);
    if (!image_data)
    {
        fprintf(stderr,
            "Error: image file not found: %s\n"
            "Place your raw application binary named 'image.bin' in the\n"
            "images/ directory, or pass --image <path>.\n", image_path);
        return 1;
    }

    char image_dir[512] = ".";
    {
        char tmp[512];
        strncpy(tmp, image_path, sizeof(tmp) - 1);
        char* separator = NULL;
        for (char* path_ptr = tmp; *path_ptr; ++path_ptr)
            if (*path_ptr == '/') separator = path_ptr;
        if (separator)
        {
            *separator = '\0';
            strncpy(image_dir, tmp, sizeof(image_dir) - 1);
        }
    }

    char keys_dir[512] = "keys";
    mkdir(keys_dir, 0755);

    printf("\n");
    for (int banner_index = 0; banner_index < 67; ++banner_index) putchar('=');
    printf("\n  Digital Signature Signing Benchmark\n");
    for (int banner_index = 0; banner_index < 67; ++banner_index) putchar('-');
    printf("\n  Input image   : %s  (%zu bytes)\n", image_path, image_size);
    printf("  Image version : %d\n", image_version);
    printf("  Keys dir      : %s\n", keys_dir);
    printf("  Output dir    : %s\n", image_dir);
    for (int banner_index = 0; banner_index < 67; ++banner_index) putchar('=');
    printf("\n");

    registry_init();
    if (filter_n > 0)
        registry_filter(filter, filter_n);

    result_t results[8];
    int n_results = 0;

    for (int entry_index = 0; entry_index < s_registry_n; ++entry_index)
    {
        if (!s_registry[entry_index].enabled)
            continue;
        if (!s_registry[entry_index].algo)
            continue;   // NULL if wolfSSL not built for it

        results[n_results++] = run_one(
            s_registry[entry_index].algo,
            image_data, image_size,
            keys_dir, image_dir,
            (uint16_t)image_version, force_keygen
        );
    }

    print_summary(results, n_results);
    free(image_data);

    /* --- random-payload benchmark ---------------------------------------- */
    rand_result_t rand_results[9 * N_RAND_SIZES];
    int n_rand = 0;
    run_random_benchmarks(image_version, keys_dir, image_dir,
                          rand_results, &n_rand);
    print_random_summary(rand_results, n_rand);

    return 0;
}
