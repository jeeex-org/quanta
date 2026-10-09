// scripts/audit/mxfp4_oracle.c
//
// Standalone oracle for MXFP4 (dtype 39) and NVFP4 (dtype 40) dequantisation.
// All dequant code, codebook tables, and scale-conversion helpers are extracted
// VERBATIM from the upstream llama.cpp source files. Prints %.17g so binary64
// round-trips.
//
// Source files (under /tmp/loader-research/llama.cpp/ggml/):
//   src/ggml-quants.c   -- dequantize_row_mxfp4 (lines 569-587)
//                         dequantize_row_nvfp4 (lines 589-612)
//   src/ggml-common.h   -- block_mxfp4 (line 215-219)
//                         block_nvfp4 (lines 221-227)
//                         QK_MXFP4=32, QK_NVFP4=64, QK_NVFP4_SUB=16
//                         kvalues_fp4 (lines 1126-1129)
//                         kvalues_mxfp4 = kvalues_fp4
//   src/ggml-impl.h     -- ggml_e8m0_to_fp32_half (lines 489-505)
//                         ggml_ue4m3_to_fp32 (lines 514-528)
//
// Build:
//   gcc -O2 -w -o /tmp/mxfp4_oracle scripts/audit/mxfp4_oracle.c -lm
//
// Usage:
//   /tmp/mxfp4_oracle mxfp4 <hex>   -- dequantize one MXFP4 block
//   /tmp/mxfp4_oracle nvfp4 <hex>   -- dequantize one NVFP4 block
//
// MXFP4 block: 17 bytes = 1 E8M0 scale byte + 16 packed E2M1 nibbles
// NVFP4 block: 36 bytes = 4 UE4M3 scale bytes + 32 packed E2M1 nibbles

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include <assert.h>

#define GGML_RESTRICT restrict
#define static_assert _Static_assert

// ---- from ggml/src/ggml-impl.h:489-505 ----
static inline float ggml_e8m0_to_fp32_half(uint8_t x) {
    uint32_t bits;

    // For x < 2: use precomputed denormal patterns
    if (x < 2) {
        // 0x00200000 = 2^(-128), 0x00400000 = 2^(-127)
        bits = 0x00200000 << x;
    }
    // For x >= 2: normalized exponent adjustment
    else {
        // 0.5 * 2^(x-127) = 2^(x-128) = normalized with exponent (x-1)
        bits = (uint32_t)(x - 1) << 23;
    }
    // Note: NaNs are not handled here

    float result;
    memcpy(&result, &bits, sizeof(float));
    return result;
}

#define GGML_E8M0_TO_FP32_HALF(x) ggml_e8m0_to_fp32_half(x)

// ---- from ggml/src/ggml-impl.h:514-528 ----
// UE4M3: unsigned, 4 exp bits (bias=7), 3 mantissa bits
// Returns value * 0.5 to match kvalues_mxfp4 convention (kvalues = 2 * E2M1_float)
static inline float ggml_ue4m3_to_fp32(uint8_t x) {
    if (x == 0 || x == 0x7F) {
        return 0.0f;
    }
    int   exp = (x >> 3) & 0xF;
    int   man = x & 0x7;
    float raw;
    if (exp == 0) {
        raw = ldexpf((float) man, -9);
    } else {
        raw = ldexpf(1.0f + (float) man / 8.0f, exp - 7);
    }
    return raw * 0.5f;
}

// ---- from ggml/src/ggml-common.h:214-227 ----
#define QK_MXFP4 32

typedef struct {
    uint8_t e;
    uint8_t qs[QK_MXFP4/2];
} block_mxfp4;

static_assert(sizeof(block_mxfp4) == sizeof(uint8_t) + QK_MXFP4/2, "wrong mxfp4 block size/padding");

#define QK_NVFP4 64
#define QK_NVFP4_SUB 16  // sub-block size for per-group scales

typedef struct {
    uint8_t d[QK_NVFP4/QK_NVFP4_SUB]; // UE4M3 scales (4 bytes, one per 16-element sub-block)
    uint8_t qs[QK_NVFP4/2];           // packed 4-bit E2M1 values (32 bytes)
} block_nvfp4;

static_assert(sizeof(block_nvfp4) == sizeof(uint8_t)*(QK_NVFP4/QK_NVFP4_SUB) + QK_NVFP4/2, "wrong nvfp4 block size/padding");

// ---- from ggml/src/ggml-common.h ----
#define GGML_TABLE_BEGIN(type, name, size) static const type name[size] = {
#define GGML_TABLE_END() };

// ---- from ggml/src/ggml-common.h:1126-1129 ----
GGML_TABLE_BEGIN(int8_t, kvalues_fp4, 16)
    0, 1, 2, 3, 4, 6, 8, 12, 0, -1, -2, -3, -4, -6, -8, -12,
GGML_TABLE_END()
#define kvalues_mxfp4 kvalues_fp4

// ---- from ggml/src/ggml-quants.c:569-587 ----
void dequantize_row_mxfp4(const block_mxfp4 * GGML_RESTRICT x, float * GGML_RESTRICT y, int64_t k) {
    static const int qk = QK_MXFP4;

    assert(k % qk == 0);

    const int nb = k / qk;

    for (int i = 0; i < nb; i++) {
        const float d = GGML_E8M0_TO_FP32_HALF(x[i].e);

        for (int j = 0; j < qk/2; ++j) {
            const int8_t x0 = kvalues_mxfp4[x[i].qs[j] & 0x0F];
            const int8_t x1 = kvalues_mxfp4[x[i].qs[j] >>   4];

            y[i*qk + j + 0   ] = x0*d;
            y[i*qk + j + qk/2] = x1*d;
        }
    }
}

// ---- from ggml/src/ggml-quants.c:589-612 ----
void dequantize_row_nvfp4(const block_nvfp4 * GGML_RESTRICT x, float * GGML_RESTRICT y, int64_t k) {
    static const int qk = QK_NVFP4;
    static const int qk_sub = QK_NVFP4_SUB;
    static const int n_sub = QK_NVFP4 / QK_NVFP4_SUB;

    assert(k % qk == 0);

    const int nb = k / qk;

    for (int i = 0; i < nb; i++) {
        for (int s = 0; s < n_sub; s++) {
            const float d = ggml_ue4m3_to_fp32(x[i].d[s]);
            float * yb = y + i*qk + s*qk_sub;

            for (int j = 0; j < qk_sub/2; ++j) {
                const int8_t v0 = kvalues_mxfp4[x[i].qs[s*(qk_sub/2) + j] & 0x0F];
                const int8_t v1 = kvalues_mxfp4[x[i].qs[s*(qk_sub/2) + j] >>   4];

                yb[j + 0       ] = v0*d;
                yb[j + qk_sub/2] = v1*d;
            }
        }
    }
}

// ---- hex decode ----
static int hexval(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static size_t hex2bin(const char *hex, uint8_t *out, size_t maxlen) {
    size_t n = 0;
    while (*hex && n < maxlen) {
        int hi = hexval(hex[0]);
        int lo = hexval(hex[1]);
        if (hi < 0 || lo < 0) break;
        out[n++] = (uint8_t)((hi << 4) | lo);
        hex += 2;
    }
    return n;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: %s mxfp4|nvfp4 <hex>\n", argv[0]);
        return 1;
    }
    const char *mode = argv[1];
    uint8_t buf[256];
    size_t len = hex2bin(argv[2], buf, sizeof(buf));
    float out[256];

    if (strcmp(mode, "mxfp4") == 0) {
        if (len != 17) { fprintf(stderr, "mxfp4 block must be 17 bytes, got %zu\n", len); return 1; }
        block_mxfp4 *blk = (block_mxfp4 *)buf;
        dequantize_row_mxfp4(blk, out, QK_MXFP4);
        for (int i = 0; i < QK_MXFP4; i++) printf("%.17g\n", out[i]);
    } else if (strcmp(mode, "nvfp4") == 0) {
        if (len != 36) { fprintf(stderr, "nvfp4 block must be 36 bytes, got %zu\n", len); return 1; }
        block_nvfp4 *blk = (block_nvfp4 *)buf;
        dequantize_row_nvfp4(blk, out, QK_NVFP4);
        for (int i = 0; i < QK_NVFP4; i++) printf("%.17g\n", out[i]);
    } else {
        fprintf(stderr, "unknown mode: %s\n", mode);
        return 1;
    }
    return 0;
}
