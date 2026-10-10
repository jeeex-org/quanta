/* blocks_oracle.c — tie-breaker for fixture expectations, using the REAL
 * dequantize_row_* from the installed ggml.
 *
 * WHY THIS FILE
 * -------------
 * Two committed expectations in tests/test_read_formats.quanta (mxfp4, nvfp4)
 * carried a sumsq matching neither upstream nor the Quanta kernel, and re-
 * deriving q5_0/q5_1 in Python disagreed with the committed values on sum and
 * sumsq while agreeing on min/max. In every one of those cases the QUESTION was
 * whether a transcription was wrong -- exactly the situation scripts/audit/
 * c_oracle.c was written to settle, and the same rule applies here: when two
 * transcriptions disagree, compile the reference and read the real bytes.
 *
 * So this links libggml-base and calls the genuine kernels on a raw block file.
 * No dequantiser is reimplemented here, which is the whole point: a third
 * hand-transcription would just be a third thing to disagree.
 *
 * usage: blocks_oracle <q4_0|q4_1|q5_0|q5_1|q8_0|mxfp4|nvfp4|iq4_nl|iq4_xs> <file>
 * prints: sum sumsq min max, then every element at %.17g
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>

#include "ggml.h"

/* ggml.h exposes the type traits but the row kernels live in ggml-quants.h,
 * which is not installed. Declare them exactly as upstream defines them. */
extern void dequantize_row_q4_0(const void *x, float *y, int64_t k);
extern void dequantize_row_q4_1(const void *x, float *y, int64_t k);
extern void dequantize_row_q5_0(const void *x, float *y, int64_t k);
extern void dequantize_row_q5_1(const void *x, float *y, int64_t k);
extern void dequantize_row_q8_0(const void *x, float *y, int64_t k);
extern void dequantize_row_mxfp4(const void *x, float *y, int64_t k);
extern void dequantize_row_nvfp4(const void *x, float *y, int64_t k);
extern void dequantize_row_iq4_nl(const void *x, float *y, int64_t k);
extern void dequantize_row_iq4_xs(const void *x, float *y, int64_t k);

typedef void (*rowfn)(const void *, float *, int64_t);

/* block_bytes and elems_per_block, both from ggml-common.h. Keeping them
 * explicit here means a format change shows up as a failed divisibility check
 * rather than as a silently wrong element count. */
struct entry { const char *name; rowfn fn; int64_t block_bytes; int64_t elems_per_block; };

static struct entry TABLE[] = {
    { "q4_0",   dequantize_row_q4_0,   18,   32 },
    { "q4_1",   dequantize_row_q4_1,   20,   32 },
    { "q5_0",   dequantize_row_q5_0,   22,   32 },
    { "q5_1",   dequantize_row_q5_1,   24,   32 },
    { "q8_0",   dequantize_row_q8_0,   34,   32 },
    { "mxfp4",  dequantize_row_mxfp4,  17,   32 },
    { "nvfp4",  dequantize_row_nvfp4,  36,   64 },
    { "iq4_nl", dequantize_row_iq4_nl, 18,   32 },
    { "iq4_xs", dequantize_row_iq4_xs, 136, 256 },
};

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "usage: blocks_oracle <fmt> <file>\n"); return 2; }

    struct entry *e = NULL;
    for (size_t i = 0; i < sizeof(TABLE)/sizeof(TABLE[0]); i++) {
        if (strcmp(TABLE[i].name, argv[1]) == 0) { e = &TABLE[i]; break; }
    }
    if (!e) { fprintf(stderr, "unknown fmt %s\n", argv[1]); return 2; }

    FILE *f = fopen(argv[2], "rb");
    if (!f) { perror("fopen"); return 1; }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (sz % e->block_bytes != 0) {
        fprintf(stderr, "file %ld bytes is not a multiple of %s block size %lld\n",
                sz, e->name, (long long)e->block_bytes);
        return 1;
    }

    int64_t nblocks = sz / e->block_bytes;
    int64_t nelem = nblocks * e->elems_per_block;
    void *raw = malloc((size_t)sz);
    if (fread(raw, 1, (size_t)sz, f) != (size_t)sz) { fprintf(stderr, "short read\n"); return 1; }
    fclose(f);

    float *y = malloc(sizeof(float) * (size_t)nelem);
    memset(y, 0, sizeof(float) * (size_t)nelem);
    e->fn(raw, y, nelem);

    double sum = 0, sumsq = 0, mn = y[0], mx = y[0];
    for (int64_t i = 0; i < nelem; i++) {
        sum  += y[i];
        sumsq += (double)y[i] * (double)y[i];
        if (y[i] < mn) mn = y[i];
        if (y[i] > mx) mx = y[i];
    }
    printf("n %lld\n", (long long)nelem);
    printf("sum %.17g\n", sum);
    printf("sumsq %.17g\n", sumsq);
    printf("min %.17g\n", mn);
    printf("max %.17g\n", mx);

    free(y);
    free(raw);
    return 0;
}