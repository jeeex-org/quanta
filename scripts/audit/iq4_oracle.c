// ===========================================================================
// iq4_oracle.c -- independent oracle for IQ4_NL and IQ4_XS dequantisation.
//
// WHY THIS EXISTS, and why it is C
// ---------------------------------
// scripts/audit/c_oracle.c already established the rule: expected values must be
// traceable to the upstream C, never to another hand transcription. Two Python
// transcriptions of dequantize_row_q5_K once disagreed while agreeing on min/max,
// so neither could be trusted.
//
// The same applies here. The two kernels below are extracted VERBATIM from the
// on-box clone at
//   /tmp/loader-research/llama.cpp/ggml/src/ggml-quants.c:2726-2765
// together with the block layouts from ggml-common.h:447-460 and the codebook
// from ggml-common.h:1120-1122. Quanta's lib/std/gguf.quanta implements the same
// two functions; this prints what upstream produces so the two can be compared
// element by element.
//
// TEST SCAFFOLDING ONLY. Not part of lib/, not linked by anything in lib/, and
// never called by the native inference path -- Quanta does not link C.
//
// Build:  gcc -O2 -w -o /tmp/iq4_oracle scripts/audit/iq4_oracle.c -lm
// Usage:  /tmp/iq4_oracle nl <hex-bytes>   (IQ4_NL, one 18-byte block)
//         /tmp/iq4_oracle xs <hex-bytes>   (IQ4_XS, one 136-byte block)
// Prints one value per line as %.17g, which round-trips a binary64 exactly --
// 9 significant digits left a ~1e-9 tolerance that is wider than the difference
// being measured, so a genuine bug and a rounding artefact looked identical.

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include <assert.h>

#define GGML_RESTRICT restrict

// The bit helpers GGML_FP16_TO_FP32 needs, declared BEFORE it uses them.
static inline float fp32_from_bits(uint32_t w) { float f; memcpy(&f, &w, 4); return f; }
static inline uint32_t fp32_to_bits(float f) { uint32_t w; memcpy(&w, &f, 4); return w; }

// ---- from ggml-common.h -----------------------------------------------------
#define QK4_NL 32
#define QK_K   256

// ggml-common.h:449-452
typedef struct {
    uint16_t d;            // ggml_half d
    uint8_t  qs[QK4_NL/2];
} block_iq4_nl;

// ggml-common.h:454-460
typedef struct {
    uint16_t d;            // ggml_half d
    uint16_t scales_h;
    uint8_t  scales_l[QK_K/64];
    uint8_t  qs[QK_K/2];
} block_iq4_xs;

// ggml-common.h:1120-1122 -- int8_t, and NOT the Q4_0 codebook.
static const int8_t kvalues_iq4nl[16] = {
    -127, -104, -83, -65, -49, -35, -22, -10, 1, 13, 25, 38, 53, 69, 89, 113,
};

// ---- GGML_FP16_TO_FP32, verbatim from ggml/src/ggml-impl.h -----------------
static inline float GGML_FP16_TO_FP32(uint16_t h) {
    const uint32_t w = (uint32_t) h << 16;
    const uint32_t sign = w & UINT32_C(0x80000000);
    const uint32_t two_w = w + w;

    const uint32_t exp_offset = UINT32_C(0xE0) << 23;
    const float exp_scale = 0x1.0p-112f;
    const float normalized_value = fp32_from_bits((two_w >> 4) + exp_offset) * exp_scale;

    const uint32_t magic_mask = UINT32_C(126) << 23;
    const float magic_bias = 0.5f;
    const float denormalized_value = fp32_from_bits((two_w >> 17) | magic_mask) - magic_bias;

    const uint32_t denormalized_cutoff = UINT32_C(1) << 27;
    const uint32_t result = sign |
        (two_w < denormalized_cutoff ? fp32_to_bits(denormalized_value) : fp32_to_bits(normalized_value));
    return fp32_from_bits(result);
}

// ---- verbatim from ggml-quants.c:2726-2742 ---------------------------------
static void dequantize_row_iq4_nl(const block_iq4_nl * GGML_RESTRICT x,
                                  float * GGML_RESTRICT y, int64_t k) {
    assert(k % QK4_NL == 0);
    const int64_t nb = k / QK4_NL;

    for (int i = 0; i < nb; i++) {

        const uint8_t * qs = x[i].qs;

        const float d = GGML_FP16_TO_FP32(x[i].d);
        for (int j = 0; j < QK4_NL/2; ++j) {
            y[j+       0] = d * kvalues_iq4nl[qs[j] & 0xf];
            y[j+QK4_NL/2] = d * kvalues_iq4nl[qs[j] >>  4];
        }
        y  += QK4_NL;
        qs += QK4_NL/2;
    }
}

// ---- verbatim from ggml-quants.c:2744-2765 ---------------------------------
static void dequantize_row_iq4_xs(const block_iq4_xs * GGML_RESTRICT x,
                                  float * GGML_RESTRICT y, int64_t k) {
    assert(k % QK_K == 0);
    const int64_t nb = k / QK_K;

    for (int i = 0; i < nb; i++) {

        const uint8_t * qs = x[i].qs;

        const float d = GGML_FP16_TO_FP32(x[i].d);

        for (int ib = 0; ib < QK_K/32; ++ib) {
            const int ls = ((x[i].scales_l[ib/2] >> 4*(ib%2)) & 0xf) | (((x[i].scales_h >> 2*ib) & 3) << 4);
            const float dl = d * (ls - 32);
            for (int j = 0; j < 16; ++j) {
                y[j+ 0] = dl * kvalues_iq4nl[qs[j] & 0xf];
                y[j+16] = dl * kvalues_iq4nl[qs[j] >>  4];
            }
            y  += 32;
            qs += 16;
        }
    }
}

// ---------------------------------------------------------------------------
static int hexnib(int c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

int main(int argc, char ** argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s nl|xs <hex>\n", argv[0]);
        return 2;
    }
    const char * mode = argv[1];
    const char * hex = argv[2];

    const size_t nhex = strlen(hex);
    if (nhex % 2) { fprintf(stderr, "odd hex length\n"); return 2; }
    const size_t n = nhex / 2;
    uint8_t * buf = (uint8_t *) malloc(n ? n : 1);
    for (size_t i = 0; i < n; i++) {
        const int hi = hexnib(hex[2*i]);
        const int lo = hexnib(hex[2*i+1]);
        if (hi < 0 || lo < 0) { fprintf(stderr, "bad hex\n"); return 2; }
        buf[i] = (uint8_t) ((hi << 4) | lo);
    }

    if (strcmp(mode, "nl") == 0) {
        if (n % sizeof(block_iq4_nl) != 0) {
            fprintf(stderr, "not a whole number of IQ4_NL blocks (block=%zu)\n",
                    sizeof(block_iq4_nl));
            return 2;
        }
        const int64_t nb = (int64_t)(n / sizeof(block_iq4_nl));
        float * y = (float *) malloc((size_t)(nb * QK4_NL) * sizeof(float));
        dequantize_row_iq4_nl((const block_iq4_nl *) buf, y, nb * QK4_NL);
        for (int64_t i = 0; i < nb * QK4_NL; i++) printf("%.17g\n", y[i]);
        free(y);
    } else if (strcmp(mode, "xs") == 0) {
        if (n % sizeof(block_iq4_xs) != 0) {
            fprintf(stderr, "not a whole number of IQ4_XS blocks (block=%zu)\n",
                    sizeof(block_iq4_xs));
            return 2;
        }
        const int64_t nb = (int64_t)(n / sizeof(block_iq4_xs));
        float * y = (float *) malloc((size_t)(nb * QK_K) * sizeof(float));
        dequantize_row_iq4_xs((const block_iq4_xs *) buf, y, nb * QK_K);
        for (int64_t i = 0; i < nb * QK_K; i++) printf("%.17g\n", y[i]);
        free(y);
    } else {
        fprintf(stderr, "unknown mode %s\n", mode);
        return 2;
    }
    free(buf);
    return 0;
}