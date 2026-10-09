// scripts/audit/mlx_affine_oracle.c
//
// Standalone oracle for MLX affine quantization dequantization.
// Extracted from Colibri's affine_quant.h (colibri/c/affine_quant.h).
//
// MLX affine format:
//   - Weights: uint32-packed unsigned values, packed along input_dim
//   - Scales: [output_dim, groups] where groups = input_dim/group_size
//   - Biases: [output_dim, groups]
//   - Dequant: out[row*I + col] = scale[row, col/gs] * q[row, col] + bias[row, col/gs]
//   - Q4: 8 values per uint32 word, 4 bits each
//   - Q8: 4 values per uint32 word, 8 bits each
//   - Little-endian uint32 words, lowest bits = lowest logical column
//
// Build:
//   gcc -O2 -w -o /tmp/mlx_affine_oracle scripts/audit/mlx_affine_oracle.c -lm
//
// Usage:
//   /tmp/mlx_affine_oracle q4 <output_dim> <input_dim> <group_size> <scales_hex> <biases_hex> <weights_hex>
//   /tmp/mlx_affine_oracle q8 <output_dim> <input_dim> <group_size> <scales_hex> <biases_hex> <weights_hex>
//
// All hex strings are little-endian byte sequences.
// Scales and biases are f32 arrays of length output_dim * groups.
// Weights are uint32 arrays of length output_dim * (input_dim / per_word).

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include <assert.h>

#define GGML_RESTRICT restrict
#define static_assert _Static_assert

// ---- from colibri/c/affine_quant.h ----

typedef enum {
    COLI_AFFINE_MLX_Q4 = 0,
    COLI_AFFINE_MLX_Q8 = 1
} ColiAffineFormat;

static inline unsigned coli_affine_bits(ColiAffineFormat format) {
    return format == COLI_AFFINE_MLX_Q4 ? 4u :
           format == COLI_AFFINE_MLX_Q8 ? 8u : 0u;
}

static inline uint32_t coli_affine_load_le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static inline float coli_affine_load_f32(const uint8_t *p) {
    uint32_t bits = coli_affine_load_le32(p);
    float f;
    memcpy(&f, &bits, 4);
    return f;
}

// ---- dequant_ref from colibri/c/affine_quant.h:238-280 ----
static inline void
coli_affine_dequant_ref(
    const uint8_t *weights, const uint8_t *scales, const uint8_t *biases,
    size_t output_dim, size_t input_dim, size_t group_size,
    ColiAffineFormat format, double *output)
{
    unsigned bits = coli_affine_bits(format);
    unsigned per_word = 32u / bits;
    uint32_t mask = (UINT32_C(1) << bits) - 1u;
    size_t groups = input_dim / group_size;

    for (size_t row = 0; row < output_dim; row++) {
        const uint8_t *weight_row =
            weights + row * (input_dim / per_word) * 4;
        double *out_row = output + row * input_dim;
        for (size_t group = 0; group < groups; group++) {
            const size_t word_base = group * (group_size / per_word);
            const size_t input_base = group * group_size;
            const size_t scalar_index = row * groups + group;
            const double scale = (double)coli_affine_load_f32(scales + scalar_index * 4);
            const double bias = (double)coli_affine_load_f32(biases + scalar_index * 4);
            for (size_t local = 0; local < group_size; local++) {
                const size_t word_index = word_base + local / per_word;
                const uint32_t word =
                    coli_affine_load_le32(weight_row + word_index * 4);
                const unsigned shift = bits * (unsigned)(local % per_word);
                out_row[input_base + local] =
                    scale * (double)((word >> shift) & mask) + bias;
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
    if (argc != 8) {
        fprintf(stderr, "usage: %s q4|q8 <output_dim> <input_dim> <group_size> <scales_hex> <biases_hex> <weights_hex>\n", argv[0]);
        return 1;
    }
    ColiAffineFormat fmt = strcmp(argv[1], "q4") == 0 ? COLI_AFFINE_MLX_Q4 :
                          strcmp(argv[1], "q8") == 0 ? COLI_AFFINE_MLX_Q8 : (ColiAffineFormat)-1;
    if ((int)fmt == -1) { fprintf(stderr, "unknown format: %s\n", argv[1]); return 1; }

    size_t output_dim = strtoul(argv[2], NULL, 10);
    size_t input_dim = strtoul(argv[3], NULL, 10);
    size_t group_size = strtoul(argv[4], NULL, 10);

    uint8_t scales_buf[65536], biases_buf[65536], weights_buf[262144];
    size_t scales_len = hex2bin(argv[5], scales_buf, sizeof(scales_buf));
    size_t biases_len = hex2bin(argv[6], biases_buf, sizeof(biases_buf));
    size_t weights_len = hex2bin(argv[7], weights_buf, sizeof(weights_buf));

    unsigned bits = coli_affine_bits(fmt);
    unsigned per_word = 32u / bits;
    size_t groups = input_dim / group_size;
    size_t expected_scales = output_dim * groups * 4;
    size_t expected_weights = output_dim * (input_dim / per_word) * 4;

    if (scales_len != expected_scales) {
        fprintf(stderr, "scales: expected %zu bytes, got %zu\n", expected_scales, scales_len);
        return 1;
    }
    if (biases_len != expected_scales) {
        fprintf(stderr, "biases: expected %zu bytes, got %zu\n", expected_scales, biases_len);
        return 1;
    }
    if (weights_len != expected_weights) {
        fprintf(stderr, "weights: expected %zu bytes, got %zu\n", expected_weights, weights_len);
        return 1;
    }

    double *output = malloc(output_dim * input_dim * sizeof(double));
    coli_affine_dequant_ref(weights_buf, scales_buf, biases_buf,
                            output_dim, input_dim, group_size, fmt, output);

    for (size_t i = 0; i < output_dim * input_dim; i++) {
        printf("%.17g\n", output[i]);
    }
    free(output);
    return 0;
}
