# Makefile — benchmark_tool
#
# Builds the benchmark_tool executable on Linux.
#
# ── wolfSSL flags ─────────────────────────────────────────────────────────
#
# Set WOLFSSL_DIR to your wolfSSL installation prefix, or install system-wide.
# The following features must be compiled into wolfSSL:
#
#   HAVE_ECC                      — ECDSA
#   WC_RSA_PSS, !NO_RSA           — RSA
#   HAVE_DILITHIUM, WOLFSSL_WC_DILITHIUM — ML-DSA-44 and ML-DSA-65
#   WOLFSSL_HAVE_LMS              — LMS
#
# Example wolfSSL ./configure line:
#
#   ./configure --enable-ecc --enable-rsapss --enable-keygen \
#     --enable-dilithium --enable-lms
#
# ── Variables ─────────────────────────────────────────────────────────────

WOLFSSL_DIR ?= /mnt/c/Users/Matyas/Desktop/Coding/ESA/wolfcrypt-py/lib/wolfssl/linux-x86_64/v5.8.4-stable

CC      ?= gcc
CFLAGS  ?= -O2 -Wall -Wextra -g
CFLAGS  += -I$(WOLFSSL_DIR)/include
# WOLFSSL_KEY_GEN enables wc_MakeRsaKey / wc_RsaKeyToDer / wc_EccKeyMake etc.
CFLAGS  += -DWOLFSSL_KEY_GEN
# Post-quantum algorithm structs are gated behind these defines
CFLAGS  += -DWOLFSSL_HAVE_LMS
CFLAGS  += -DHAVE_DILITHIUM -DWOLFSSL_WC_DILITHIUM
LDFLAGS += -L$(WOLFSSL_DIR)/lib -lwolfssl -lm

TARGET  = benchmark_tool

SRCS = \
    main.c            \
    io_utils.c         \
    binary_processor.c \
    sig_ecdsa.c        \
    sig_rsa.c          \
    sig_mldsa.c        \
    sig_lms.c          \

OBJS = $(SRCS:.c=.o)

# ── Rules ──────────────────────────────────────────────────────────────────

.PHONY: all clean run

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

clean:
	rm -f $(OBJS) $(TARGET)

# Quick smoke-test: sign the provided image.bin (must exist next to Makefile)
run: $(TARGET)
	./$(TARGET) --image image.bin

# ── Dependencies (simplified; use gcc -MM to regenerate) ──────────────────

main.c:             binary_processor.h sig_algo.h sig_ecdsa.h sig_rsa.h \
                    sig_mldsa.h sig_lms.h
binary_processor.c: binary_processor.h sig_algo.h
io_utils.c:         io_utils.h
sig_ecdsa.c:        sig_ecdsa.h sig_algo.h
sig_rsa.c:          sig_rsa.h   sig_algo.h
sig_mldsa.c:        sig_mldsa.h sig_algo.h
sig_lms.c:          sig_lms.h   sig_algo.h
