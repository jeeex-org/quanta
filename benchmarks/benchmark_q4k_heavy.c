// C Q4_K matmul benchmark - bigger
//
// Twin repair (0.0.238): identical in kind to benchmark_q4k.c -- see the long
// comment there. Summary: this derived C side used `1 << shift` where its Quanta
// twin uses `1 * shift` (so scale_q8 was 0 here and 24 there), AND it used C
// truncation where the language under test defines `/` as floor
// (`-3624 / 128` = -28 here, -29 in Quanta). Both are fixed so the two sides
// compute the same function; outputs now agree exactly.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define Q8_SCALE 128
// floor(a / b) for b > 0 -- Quanta's integer-division semantics.
static long qdiv(long a, long b) {
    long q = a / b;
    if (q * b != a && (a < 0) != (b < 0)) q--;
    return q;
}
int f16_to_q8(int f16) {
    int sign = (int)qdiv(f16, 32768) * 32768;
    int exp = (int)qdiv(f16 - sign, 1024);
    int mant = f16 - sign - exp * 1024;
    if (exp == 0) { if (mant == 0) return 0; return (int)qdiv((long)mant * Q8_SCALE, 1048576); }
    if (exp == 31) return 0;
    int base = 1024 + mant;
    int shift = exp - 15;
    if (shift >= 0) return (int)qdiv((long)base * (1 * shift) * Q8_SCALE, 1024);
    else return (int)qdiv(qdiv((long)base * Q8_SCALE, 1024), 1 * (-shift));
}
void dequant_q4k(unsigned char *W, long *out) {
    int scale_q8 = f16_to_q8(W[0] + W[1] * 256);
    for (int qi = 0; qi < 256; qi++) {
        int sub_q8 = W[2 + qi / 16];
        int byte_val = W[18 + qi / 2];
        int nibble = (qi % 2 == 0) ? (byte_val % 16) : (byte_val / 16);
        out[qi] = qdiv((long)scale_q8 * sub_q8 * (nibble - 8), Q8_SCALE);
    }
}
void matvec_q4k(unsigned char *W, long *x, int rows, int cols, long *y) {
    int n_blocks = cols / 256;
    long dequant[256];
    for (int i = 0; i < rows; i++) {
        long sum = 0;
        for (int bi = 0; bi < n_blocks; bi++) {
            dequant_q4k(W + (i * n_blocks + bi) * 144, dequant);
            for (int j = 0; j < 256; j++) {
                sum += qdiv(dequant[j] * x[bi * 256 + j], Q8_SCALE);
            }
        }
        y[i] = sum;
    }
}
int main() {
    int rows = 100, cols = 2560, n_blocks = cols / 256;
    unsigned char *W = malloc(rows * n_blocks * 144);
    long *x = malloc(cols * 8), *y = malloc(rows * 8);
    memset(W, 0x97, rows * n_blocks * 144);
    for (int i = 0; i < cols; i++) x[i] = 128;
    matvec_q4k(W, x, rows, cols, y);
    printf("result[0]=%ld\n", y[0]);
    free(W); free(x); free(y);
    return 0;
}
