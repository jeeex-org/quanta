// qg_test.cu — verify the GPU kernels against the CPU reference.
//
// The point of this harness is BIT-EXACT agreement with lib/std/gguf.quanta's
// CPU dequant, so a GPU/CPU comparison is a real check rather than a tolerance
// exercise. It reimplements the CPU side here in plain C, transcribed from the
// same source the kernel was transcribed from, and compares byte for byte.
//
// Build:  nvcc -O2 -arch=sm_89 qg_test.cu quanta_gpu_kernels.cu -o qg_test

#include <cuda_runtime.h>
#include <cuda_fp16.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>

extern "C" int qg_dequant(int dtype, const void *raw, float *out, long nelem);
extern "C" int qg_matvec(int dtype, const void *w, const float *x, float *y,
                         long rows, long cols);

// ---- CPU reference: q4k_sc/q4k_min/dequant_q4k, mirroring gguf.quanta ------
static int cpu_q4k_sc(int j, const unsigned char *sc) {
    if (j < 4) return sc[j] & 63;
    return (sc[j + 4] & 0x0F) | ((sc[j - 4] >> 6) << 4);
}
static int cpu_q4k_min(int j, const unsigned char *sc) {
    if (j < 4) return sc[j + 4] & 63;
    return (sc[j + 4] >> 4) | ((sc[j] >> 6) << 4);
}
static float half_to_float(uint16_t h) {
    __half hh; memcpy(&hh, &h, 2); return __half2float(hh);
}
static void cpu_dequant_q4k(const unsigned char *raw, long nelem, float *out) {
    long nblocks = nelem / 256;
    for (long bi = 0; bi < nblocks; bi++) {
        const unsigned char *bo = raw + bi * 144;
        uint16_t dh, dmh;
        memcpy(&dh, bo + 0, 2); memcpy(&dmh, bo + 2, 2);
        float d = half_to_float(dh), dmin = half_to_float(dmh);
        const unsigned char *sc = bo + 4;
        const unsigned char *q = bo + 16;
        float *o = out + bi * 256;
        int is = 0;
        for (int chunk = 0; chunk < 4; chunk++) {
            float d1 = d * (float)cpu_q4k_sc(is, sc);
            float mm1 = dmin * (float)cpu_q4k_min(is, sc);
            float d2 = d * (float)cpu_q4k_sc(is + 1, sc);
            float mm2 = dmin * (float)cpu_q4k_min(is + 1, sc);
            const unsigned char *qs = q + chunk * 32;
            float *o0 = o + chunk * 64, *o1 = o0 + 32;
            for (int l = 0; l < 32; l++) {
                int byte = qs[l];
                o0[l] = d1 * (float)(byte & 0x0F) - mm1;
                o1[l] = d2 * (float)(byte >> 4) - mm2;
            }
            is += 2;
        }
    }
}

static uint64_t rng_state = 0x243F6A8885A308D3ull;
static uint64_t rng(void) {
    rng_state ^= rng_state << 13; rng_state ^= rng_state >> 7; rng_state ^= rng_state << 17;
    return rng_state;
}

int main(void) {
    int fail = 0;

    // ---- 1. dequant: bit-exact against the CPU reference ----
    const long NBLK = 512;                 // 512 super-blocks = 131072 elements
    const long NELEM = NBLK * 256;
    unsigned char *raw = (unsigned char *)malloc(NBLK * 144);
    float *cpu_out = (float *)malloc(NELEM * sizeof(float));
    float *gpu_out = (float *)malloc(NELEM * sizeof(float));

    for (long i = 0; i < NBLK * 144; i++) raw[i] = (unsigned char)(rng() & 0xFF);
    // Keep the f16 scales in a sane range: a random bit pattern can be inf/NaN,
    // and NaN != NaN would make the comparison meaningless rather than wrong.
    for (long b = 0; b < NBLK; b++) {
        uint16_t d = (uint16_t)((rng() % 1024) | 0x2000);   // small normal halves
        uint16_t dm = (uint16_t)((rng() % 1024) | 0x2000);
        memcpy(raw + b * 144 + 0, &d, 2);
        memcpy(raw + b * 144 + 2, &dm, 2);
    }

    cpu_dequant_q4k(raw, NELEM, cpu_out);

    unsigned char *d_raw = NULL;
    float *d_out = NULL;
    cudaMalloc(&d_raw, NBLK * 144);
    cudaMalloc(&d_out, NELEM * sizeof(float));
    cudaMemcpy(d_raw, raw, NBLK * 144, cudaMemcpyHostToDevice);
    if (qg_dequant(12, d_raw, d_out, NELEM) != 0) {
        printf("FAIL: qg_dequant returned an error\n"); return 1;
    }
    cudaMemcpy(gpu_out, d_out, NELEM * sizeof(float), cudaMemcpyDeviceToHost);

    long diff = 0; long first = -1;
    for (long i = 0; i < NELEM; i++) {
        if (memcmp(&cpu_out[i], &gpu_out[i], 4) != 0) {
            if (first < 0) first = i;
            diff++;
        }
    }
    printf("dequant Q4_K: %ld elements, bit-differing=%ld\n", NELEM, diff);
    if (diff) {
        printf("  first at %ld: cpu=%a gpu=%a\n", first, cpu_out[first], gpu_out[first]);
        fail = 1;
    }

    // ---- 2. matvec (fused dequant) vs a CPU matvec over the CPU dequant ----
    const long ROWS = 64, COLS = 512;      // 512 = 2 super-blocks per row
    const long RBLK = COLS / 256;
    unsigned char *w = (unsigned char *)malloc(ROWS * RBLK * 144);
    memcpy(w, raw, ROWS * RBLK * 144);     // reuse the same random blocks
    float *x = (float *)malloc(COLS * sizeof(float));
    float *cpu_y = (float *)malloc(ROWS * sizeof(float));
    float *gpu_y = (float *)malloc(ROWS * sizeof(float));
    float *w_deq = (float *)malloc(ROWS * COLS * sizeof(float));

    for (long i = 0; i < COLS; i++) x[i] = (float)((int)(rng() % 2000) - 1000) / 512.0f;
    cpu_dequant_q4k(w, ROWS * COLS, w_deq);
    for (long r = 0; r < ROWS; r++) {
        double acc = 0.0;
        for (long c = 0; c < COLS; c++) acc += (double)w_deq[r * COLS + c] * (double)x[c];
        cpu_y[r] = (float)acc;
    }

    unsigned char *d_w = NULL; float *d_x = NULL, *d_y = NULL;
    cudaMalloc(&d_w, ROWS * RBLK * 144);
    cudaMalloc(&d_x, COLS * sizeof(float));
    cudaMalloc(&d_y, ROWS * sizeof(float));
    cudaMemcpy(d_w, w, ROWS * RBLK * 144, cudaMemcpyHostToDevice);
    cudaMemcpy(d_x, x, COLS * sizeof(float), cudaMemcpyHostToDevice);
    if (qg_matvec(12, d_w, d_x, d_y, ROWS, COLS) != 0) {
        printf("FAIL: qg_matvec returned an error\n"); return 1;
    }
    cudaMemcpy(gpu_y, d_y, ROWS * sizeof(float), cudaMemcpyDeviceToHost);

    // The kernel accumulates in f32 with a different summation order than the
    // f64 CPU sum, so an exact match is not expected here; the check is that
    // the relative error is at f32 round-off level.
    double worst = 0.0; long worst_r = -1;
    for (long r = 0; r < ROWS; r++) {
        double denom = fabs((double)cpu_y[r]) > 1e-30 ? fabs((double)cpu_y[r]) : 1e-30;
        double rel = fabs((double)gpu_y[r] - (double)cpu_y[r]) / denom;
        if (rel > worst) { worst = rel; worst_r = r; }
    }
    printf("matvec Q4_K: %ld rows, worst relative error=%.3e (row %ld)\n", ROWS, worst, worst_r);
    printf("  cpu_y[%ld]=%a gpu_y[%ld]=%a\n", worst_r, cpu_y[worst_r], worst_r, gpu_y[worst_r]);
    if (worst > 1e-5) { printf("  FAIL: relative error too large\n"); fail = 1; }

    // ---- 3. F32 matvec sanity ----
    {
        const long R2 = 32, C2 = 1024;
        float *fw = (float *)malloc(R2 * C2 * sizeof(float));
        float *fx = (float *)malloc(C2 * sizeof(float));
        float *fy = (float *)malloc(R2 * sizeof(float));
        float *cy = (float *)malloc(R2 * sizeof(float));
        for (long i = 0; i < R2 * C2; i++) fw[i] = (float)((int)(rng() % 2000) - 1000) / 1024.0f;
        for (long i = 0; i < C2; i++) fx[i] = (float)((int)(rng() % 2000) - 1000) / 1024.0f;
        for (long r = 0; r < R2; r++) {
            double acc = 0.0;
            for (long c = 0; c < C2; c++) acc += (double)fw[r * C2 + c] * (double)fx[c];
            cy[r] = (float)acc;
        }
        float *d_fw = NULL, *d_fx = NULL, *d_fy = NULL;
        cudaMalloc(&d_fw, R2 * C2 * sizeof(float));
        cudaMalloc(&d_fx, C2 * sizeof(float));
        cudaMalloc(&d_fy, R2 * sizeof(float));
        cudaMemcpy(d_fw, fw, R2 * C2 * sizeof(float), cudaMemcpyHostToDevice);
        cudaMemcpy(d_fx, fx, C2 * sizeof(float), cudaMemcpyHostToDevice);
        if (qg_matvec(0, d_fw, d_fx, d_fy, R2, C2) != 0) { printf("FAIL: f32 matvec\n"); return 1; }
        cudaMemcpy(fy, d_fy, R2 * sizeof(float), cudaMemcpyDeviceToHost);
        double w2 = 0.0;
        for (long r = 0; r < R2; r++) {
            double denom = fabs((double)cy[r]) > 1e-30 ? fabs((double)cy[r]) : 1e-30;
            double rel = fabs((double)fy[r] - (double)cy[r]) / denom;
            if (rel > w2) w2 = rel;
        }
        printf("matvec F32: %ld rows, worst relative error=%.3e\n", R2, w2);
        if (w2 > 1e-5) { printf("  FAIL: relative error too large\n"); fail = 1; }
    }

    printf(fail ? "\nqg_test: FAIL\n" : "\nqg_test: PASS\n");
    return fail;
}
