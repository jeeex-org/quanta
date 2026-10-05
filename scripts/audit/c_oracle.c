// Compiled oracle: reads a tensor out of a real GGUF and reduces it with the
// SAME dequantize_row_* algorithm as upstream llama.cpp.
//
// WHY THIS EXISTS
// ---------------
// Two hand-written Python transcriptions of dequantize_row_q5_K disagreed on
// sum/sumsq while AGREEING on min/max. When two oracles disagree, neither can
// be trusted -- so this compiles the reference algorithm and reads the real
// bytes. The Python oracle (read_formats_oracle.py) stays human-readable; this
// one is the tie-breaker and the source of the expected values baked into
// tests/test_read_formats.quanta.
//
// This is TEST SCAFFOLDING ONLY. It is not part of lib/ and the native
// inference path never calls it -- Quanta does not link C. It exists so that
// every expected value in the Quanta tests is traceable to the upstream C
// rather than to another transcription of it.
//
// GGUF v3 layout (all scalars fixed-width little-endian, NOT varints):
//   magic u32, version u32, n_tensors u64, n_kv u64
//   kv:   key(string), type u32, value
//   ti:   name(string), n_dims u32, dims[n_dims] u64, dtype u32, offset u64
//   data: aligned up to general.alignment
//
// Build: gcc -O2 -w -o /tmp/cora scripts/audit/c_oracle.c -lm
// Usage: /tmp/cora <file.gguf> <tensor_name> [n_elements]

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>

// Real ggml: fp16 conversion and the authoritative dequantize_row_* kernels.
#include "ggml.h"

// dequantize_row_* are exported from libggml-base but not declared in any
// installed ggml header, so declare them here rather than reimplementing them.
// block_q5_K / block_q8_0 come from ggml-common.h via ggml.h.
// The block types live in ggml-common.h, which is not part of the installed
// include dir, so the prototypes take void* and the casts happen at the call.
extern void dequantize_row_q5_K(const void *, float *, int64_t);
extern void dequantize_row_q8_0(const void *, float *, int64_t);

#define QK_K   256
#define K_SCALE_SIZE 12
#define QK8_0  32

// ---- block layouts, copied verbatim from ggml/src/ggml-common.h ----
typedef struct {
    uint16_t d;                        // union with { d, dmin }
    uint16_t dmin;
    uint8_t  scales[K_SCALE_SIZE];
    uint8_t  qh[QK_K/8];
    uint8_t  qs[QK_K/2];
} block_q5_K;
typedef struct {
    uint16_t d;
    int8_t   qs[QK8_0];
} block_q8_0;

static uint32_t rd32(const uint8_t *p){ return (uint32_t)p[0]|(p[1]<<8)|(p[2]<<16)|((uint32_t)p[3]<<24); }
static uint64_t rd64(const uint8_t *p){ return (uint64_t)rd32(p) | ((uint64_t)rd32(p+4)<<32); }

// TEST SCAFFOLDING ONLY -- links the prebuilt libggml-base for the real
// GGML_FP16_TO_FP32. An earlier version of this file hand-rolled half->float
// and got the SUBNORMAL case wrong (2x on Q5_K d, 0.5x on dmin), which is the
// entire class of bug this file exists to catch -- so it must not hand-roll it.
// The linked symbol is ggml_fp16_to_fp32, matching GGML_FP16_TO_FP32 in ggml.h.
static inline float fp16_to_fp32(uint16_t h) { return ggml_fp16_to_fp32(h); }


static void deq_q5k(const void *base, float *y, int64_t k) {
    dequantize_row_q5_K(base, y, k);
}
static void deq_q8_0(const void *base, float *y, int64_t k) {
    dequantize_row_q8_0(base, y, k);
}

static int64_t skip_value(const uint8_t *m, int64_t o, uint32_t t) {
    switch (t) {
        case 0: case 1: return o + 1;    // UINT8,  INT8
        case 2: case 3: return o + 2;    // UINT16, INT16
        case 4: case 5: return o + 4;    // UINT32, INT32
        case 6:          return o + 4;    // FLOAT32
        case 7:          return o + 1;    // BOOL
        case 8: { uint64_t n = rd64(m+o); return o + 8 + (int64_t)n; }  // STRING
        case 9: {                                      // ARRAY
            uint32_t et = rd32(m+o); o += 4;
            uint64_t n  = rd64(m+o); o += 8;
            // Arrays of STRING/ARRAY do not occur in the keys we scan.
            if (et == 8) { for (uint64_t k = 0; k < n; k++) { uint64_t l = rd64(m+o); o += 8 + (int64_t)l; } return o; }
            int64_t esz = (et <= 1) ? 1 : (et <= 3) ? 2 : (et <= 7) ? 4 : (et <= 11) ? 8 : 0;
            return o + (int64_t)n * esz;
        }
        case 10: case 11: return o + 8;  // UINT64, INT64
        case 12:          return o + 8;  // FLOAT64
        default:          return o;      // unknown type: cannot skip safely
    }
}

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s file.gguf tensor [n]\n", argv[0]); return 2; }
    long want = argc > 3 ? atol(argv[3]) : 4096;

    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("open"); return 2; }
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *m = malloc(sz);
    if (fread(m, 1, sz, f) != (size_t)sz) { fprintf(stderr, "short read\n"); return 2; }
    fclose(f);

    if (memcmp(m, "GGUF", 4)) { fprintf(stderr, "not GGUF\n"); return 2; }
    if (rd32(m+4) != 3)       { fprintf(stderr, "not GGUF v3\n"); return 2; }

    int64_t o = 8;
    uint64_t ntens = rd64(m+o); o += 8;
    uint64_t nkv   = rd64(m+o); o += 8;

    uint64_t align = 32;                 // GGUF_DEFAULT_ALIGNMENT
    for (uint64_t i = 0; i < nkv; i++) {
        uint64_t klen = rd64(m+o);
        char key[128];
        uint64_t cl = klen < sizeof(key) - 1 ? klen : sizeof(key) - 1;
        memcpy(key, m + o + 8, cl); key[cl] = 0;
        o += 8 + (int64_t)klen;
        uint32_t vt = rd32(m+o); o += 4;
        if (!strcmp(key, "general.alignment") && vt == 4) align = rd32(m + o);
        o = skip_value(m, o, vt);
    }
    const uint64_t align_ten = align;

    // Two passes on purpose: the tensor data section starts after the END of
    // every tensor-info record, so we must walk them all before we know where
    // the data lives. Stopping at the matching name (single pass) yields a data
    // offset that is short by the size of the remaining records -- which reads
    // garbage that still looks like plausible weights.
    uint32_t want_tt = 0; uint64_t want_off = 0, want_ne = 0;
    int found = 0;
    for (uint64_t i = 0; i < ntens; i++) {
        uint64_t nlen = rd64(m+o); o += 8;
        int hit = (nlen == strlen(argv[2]) && !memcmp(m+o, argv[2], nlen));
        o += nlen;
        uint32_t nd = rd32(m+o); o += 4;
        uint64_t ne = 1;
        for (uint32_t k = 0; k < nd; k++) { ne *= rd64(m+o); o += 8; }
        uint32_t tt  = rd32(m+o); o += 4;
        uint64_t off = rd64(m+o); o += 8;
        if (hit) { want_tt = tt; want_off = off; want_ne = ne; found = 1; }
    }
    int64_t data_off = (o + (int64_t)align_ten - 1) & ~((int64_t)align_ten - 1);
    if (!found) { fprintf(stderr, "tensor not found\n"); return 4; }

    {
        long n = want < (long)want_ne ? want : (long)want_ne;
        const uint8_t *base = m + data_off + want_off;
        float *y = malloc((size_t)n * 4);
        if      (want_tt == 13) deq_q5k(base, y, n);
        else if (want_tt == 8)  deq_q8_0(base, y, n);
        else { fprintf(stderr, "dtype %u not built into this oracle\n", want_tt); return 3; }

        double s = 0, sq = 0;
        float mn = y[0], mx = y[0];
        for (long k = 0; k < n; k++) {
            s += y[k]; sq += (double)y[k]*y[k];
            if (y[k] < mn) mn = y[k];
            if (y[k] > mx) mx = y[k];
        }
        printf("dtype=%u ne=%llu n=%ld\n", want_tt, (unsigned long long)want_ne, n);
        printf("first=");
        for (long k = 0; k < 6 && k < n; k++) printf("%.6f ", y[k]);
        printf("\n");
        printf("sum=%.6f sumsq=%.6f min=%.6f max=%.6f\n", s, sq, mn, mx);
        return 0;
    }
}