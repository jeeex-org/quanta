// quanta_gpu_kernels.cu — dequant + matvec kernels for Quanta Phase 6.2.
//
// WHY THIS IS A SEPARATE TRANSLATION UNIT
// ---------------------------------------
// The daemon (cuda_daemon.c) is plain C and links only cudart, so it can
// allocate and copy but cannot launch anything. Device code needs nvcc. Keeping
// the kernels here means the daemon's build stays a one-line gcc, and this file
// is the only thing that needs the CUDA compiler.
//
// It exposes two plain C entry points that the daemon calls through ordinary
// function calls (same process, same context), so no ABI beyond `extern "C"`:
//
//   int qg_dequant(int dtype, const void *raw, float *out, long nelem);
//   int qg_matvec(int dtype, const void *w, const float *x, float *y,
//                 long rows, long cols);
//
// NUMERICS: the goal is to match lib/std/gguf.quanta's CPU dequant bit for bit,
// so a GPU/CPU comparison is a real check and not a tolerance exercise. Every
// constant below is transcribed from that file's Q4_K body, which was itself
// checked value-for-value against the real model tensor.

#include <cuda_runtime.h>
#include <cuda_fp16.h>
#include <stdio.h>

#define CUDA_CHECK(call)                                                       \
    do {                                                                       \
        cudaError_t _e = (call);                                               \
        if (_e != cudaSuccess) {                                               \
            fprintf(stderr, "quanta_gpu: %s failed: %s\n", #call,              \
                    cudaGetErrorString(_e));                                   \
            return -1;                                                         \
        }                                                                      \
    } while (0)

// ---------------------------------------------------------------------------
// Q4_K (ggml type 12). 144-byte super-block -> 256 f32 weights.
//   +0  f16 d       super-block scale for the 6-bit sub-scales
//   +2  f16 dmin    super-block scale for the 6-bit sub-mins
//   +4  u8  scales[12]  eight (scale, min) pairs, 6 bits each, bit-packed
//   +16 u8  qs[128]     4-bit quants, low nibble = even element, high = odd
//
// q4k_sc/q4k_min mirror get_scale_min_k4() from ggml-quants.c, and mirror
// gguf.quanta's q4k_sc/q4k_min exactly. The j>=4 cases are the ones that are
// easy to get wrong: the scale's high bits come from sc[j-4] but the min's high
// bits come from sc[j]. Swapping them mis-pairs every sub-block from 4 up and
// still produces plausible-looking numbers.
// ---------------------------------------------------------------------------
__device__ __forceinline__ int q4k_sc(int j, const unsigned char *sc) {
    if (j < 4) return sc[j] & 63;
    return (sc[j + 4] & 0x0F) | ((sc[j - 4] >> 6) << 4);
}

__device__ __forceinline__ int q4k_min(int j, const unsigned char *sc) {
    if (j < 4) return sc[j + 4] & 63;
    return (sc[j + 4] >> 4) | ((sc[j] >> 6) << 4);
}

// Dequantize `nelem` elements (a multiple of 256) of Q4_K from `raw` into `out`.
// One thread per super-block: 256 weights is 4 chunks x 64, and the block is
// read once. That is 256 floats written per thread, which is a lot of work per
// thread but keeps the scale decode (the expensive part) to one per block
// instead of spreading it across 256 threads that would each redo it.
__global__ void dequant_q4k_kernel(const unsigned char *__restrict__ raw,
                                   float *__restrict__ out, long nblocks) {
    long b = (long)blockIdx.x * blockDim.x + threadIdx.x;
    if (b >= nblocks) return;

    const unsigned char *blk = raw + b * 144;
    const __half *dh = (const __half *)blk;
    // f16 -> f32. The CPU path goes through f16_to_f64; both are exact for a
    // half, so the f32 result is identical.
    const float d    = __half2float(dh[0]);
    const float dmin = __half2float(dh[1]);
    const unsigned char *sc = blk + 4;
    const unsigned char *q  = blk + 16;
    float *o = out + b * 256;

    int is = 0;
    for (int chunk = 0; chunk < 4; chunk++) {
        const float d1  = d * (float)q4k_sc(is, sc);
        const float mm1 = dmin * (float)q4k_min(is, sc);
        const float d2  = d * (float)q4k_sc(is + 1, sc);
        const float mm2 = dmin * (float)q4k_min(is + 1, sc);

        // 32 bytes hold 64 elements: low nibbles are the even half of the first
        // 32-element sub-block, high nibbles the second.
        const unsigned char *qs = q + chunk * 32;
        float *o0 = o + chunk * 64;
        float *o1 = o0 + 32;
        for (int l = 0; l < 32; l++) {
            const int byte = qs[l];
            const int lo = byte & 0x0F;
            const int hi = byte >> 4;
            o0[l] = d1 * (float)lo - mm1;
            o1[l] = d2 * (float)hi - mm2;
        }
        is += 2;
    }
}

// ---------------------------------------------------------------------------
// F32 matvec: y[row] = sum_col W[row*cols + col] * x[col]
//
// One warp per row. A warp-wide reduction with __shfl_down_sync keeps this to
// one block-wide write per row and needs no shared memory. Lane stride of
// blockDim.y over the row keeps the loads coalesced.
// ---------------------------------------------------------------------------
__global__ void matvec_f32_kernel(const float *__restrict__ W,
                                  const float *__restrict__ x,
                                  float *__restrict__ y,
                                  long rows, long cols) {
    const long row = blockIdx.x;
    if (row >= rows) return;
    const float *w = W + row * cols;

    float acc = 0.0f;
    for (long c = threadIdx.x; c < cols; c += blockDim.x) acc += w[c] * x[c];

    // Warp reduction.
    for (int off = 16; off > 0; off >>= 1)
        acc += __shfl_down_sync(0xFFFFFFFFu, acc, off);

    __shared__ float s[32];
    const int warp = threadIdx.x >> 5;
    const int lane = threadIdx.x & 31;
    if (lane == 0) s[warp] = acc;
    __syncthreads();

    if (warp == 0) {
        const int nwarps = (blockDim.x + 31) >> 5;
        float v = (lane < nwarps) ? s[lane] : 0.0f;
        for (int off = 16; off > 0; off >>= 1)
            v += __shfl_down_sync(0xFFFFFFFFu, v, off);
        if (lane == 0) y[row] = v;
    }
}

// ---------------------------------------------------------------------------
// Fused dequant + matvec for Q4_K: y[row] = sum_col dequant(W)[row*cols+col]*x[col]
//
// Reading the weights once from global memory and dequantizing in registers
// avoids materialising the f32 matrix. For a 2.6B model that materialisation is
// ~10 GB, which is the whole reason this kernel exists.
//
// One block per row; each thread strides over the row's super-blocks.
// ---------------------------------------------------------------------------
__global__ void matvec_q4k_kernel(const unsigned char *__restrict__ W,
                                  const float *__restrict__ x,
                                  float *__restrict__ y,
                                  long rows, long cols) {
    const long row = blockIdx.x;
    if (row >= rows) return;
    const long blocks_per_row = cols / 256;
    const unsigned char *wrow = W + row * blocks_per_row * 144;

    float acc = 0.0f;
    for (long b = threadIdx.x; b < blocks_per_row; b += blockDim.x) {
        const unsigned char *blk = wrow + b * 144;
        const __half *dh = (const __half *)blk;
        const float d    = __half2float(dh[0]);
        const float dmin = __half2float(dh[1]);
        const unsigned char *sc = blk + 4;
        const unsigned char *q  = blk + 16;
        const float *xb = x + b * 256;

        int is = 0;
        for (int chunk = 0; chunk < 4; chunk++) {
            const float d1  = d * (float)q4k_sc(is, sc);
            const float mm1 = dmin * (float)q4k_min(is, sc);
            const float d2  = d * (float)q4k_sc(is + 1, sc);
            const float mm2 = dmin * (float)q4k_min(is + 1, sc);

            const unsigned char *qs = q + chunk * 32;
            const float *x0 = xb + chunk * 64;
            const float *x1 = x0 + 32;
            #pragma unroll
            for (int l = 0; l < 32; l++) {
                const int byte = qs[l];
                acc += (d1 * (float)(byte & 0x0F) - mm1) * x0[l];
                acc += (d2 * (float)(byte >> 4) - mm2) * x1[l];
            }
            is += 2;
        }
    }

    for (int off = 16; off > 0; off >>= 1)
        acc += __shfl_down_sync(0xFFFFFFFFu, acc, off);

    __shared__ float s[32];
    const int warp = threadIdx.x >> 5;
    const int lane = threadIdx.x & 31;
    if (lane == 0) s[warp] = acc;
    __syncthreads();

    if (warp == 0) {
        const int nwarps = (blockDim.x + 31) >> 5;
        float v = (lane < nwarps) ? s[lane] : 0.0f;
        for (int off = 16; off > 0; off >>= 1)
            v += __shfl_down_sync(0xFFFFFFFFu, v, off);
        if (lane == 0) y[row] = v;
    }
}

// ---------------------------------------------------------------------------
// f32 <-> f64 conversion.
//
// Both directions are EXACT (f32 -> f64 is exact by definition; f64 -> f32 is a
// genuine narrowing, which is what the device wants for weights). They exist as
// kernels rather than host loops because the loader's buffers are already on
// the device: a host loop would mean a d2h, a convert, and an h2d for every
// tensor.
// ---------------------------------------------------------------------------
__global__ void f32_to_f64_kernel(const float *__restrict__ src,
                                  double *__restrict__ dst, long n) {
    long i = (long)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) dst[i] = (double)src[i];
}

__global__ void f64_to_f32_kernel(const double *__restrict__ src,
                                  float *__restrict__ dst, long n) {
    long i = (long)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) dst[i] = (float)src[i];
}

// ---------------------------------------------------------------------------
// Plain-C entry points for the daemon.
// ---------------------------------------------------------------------------

extern "C" int qg_dequant(int dtype, const void *raw, float *out, long nelem) {
    if (dtype != 12) return -1;              // Q4_K only for now
    if (nelem <= 0 || (nelem % 256) != 0) return -2;
    const long nblocks = nelem / 256;
    const int threads = 128;
    const long blocks = (nblocks + threads - 1) / threads;
    dequant_q4k_kernel<<<(unsigned)blocks, threads>>>(
        (const unsigned char *)raw, out, nblocks);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());
    return 0;
}

extern "C" int qg_f32_to_f64(const float *src, double *dst, long n) {
    if (n <= 0) return -2;
    const int threads = 256;
    const long blocks = (n + threads - 1) / threads;
    f32_to_f64_kernel<<<(unsigned)blocks, threads>>>(src, dst, n);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());
    return 0;
}

extern "C" int qg_f64_to_f32(const double *src, float *dst, long n) {
    if (n <= 0) return -2;
    const int threads = 256;
    const long blocks = (n + threads - 1) / threads;
    f64_to_f32_kernel<<<(unsigned)blocks, threads>>>(src, dst, n);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());
    return 0;
}

extern "C" int qg_matvec(int dtype, const void *w, const float *x, float *y,
                         long rows, long cols) {
    if (rows <= 0 || cols <= 0) return -2;
    const int threads = 256;
    if (dtype == 0) {                        // F32
        matvec_f32_kernel<<<(unsigned)rows, threads>>>(
            (const float *)w, x, y, rows, cols);
    } else if (dtype == 12) {                // Q4_K
        if ((cols % 256) != 0) return -3;
        matvec_q4k_kernel<<<(unsigned)rows, threads>>>(
            (const unsigned char *)w, x, y, rows, cols);
    } else {
        return -1;
    }
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());
    return 0;
}
