// C Q4_K matmul benchmark
//
// Twin repair (0.0.238). This C side is the DERIVED artifact, and it had two
// derivation errors that made it compute a DIFFERENT FUNCTION from the Quanta
// program it is paired with, so the row's two outputs disagreed:
//
//  1. ALGORITHM. The Quanta twin computes `base * (1 * (-shift)) * Q8_SCALE / 1024`
//     -- a plain multiply by the shift amount -- while this file used
//     `base * (1 << (-shift)) * Q8_SCALE / 1024`, i.e. 2^shift. For the
//     benchmark's input (W = 0x97) that is scale_q8 = 24 on the Quanta side and 0
//     here, so the two sides were not executing the same shape at all. This file
//     now uses the SAME arithmetic as the Quanta program it mirrors.
//  2. SEMANTICS. Quanta's `/` is FLOOR and `%` takes the DIVISOR's sign; C
//     truncates toward zero. `-3624 / 128` is -29 in Quanta and -28 in C, and the
//     dequant numerator is negative for half the nibbles, so even with the same
//     algorithm the printed values differ. `qdiv()` implements floor for a
//     positive divisor, so this twin computes what its Quanta counterpart computes.
//
// With both fixed the two sides agree exactly: -1280 (Quanta) and -1280 (here).
// Cross-checked in Python, which reproduces both the old and the new value from
// the two sources rather than trusting either program.
//
// NOTE: the Quanta expression `(1 * shift)` looks like a typo for `(1 << shift)`
// (2^shift is the standard FP16 exponent scale and `<<` is used throughout
// lib/std). That is a separate BENCHMARK-DATA question: correcting it makes the
// scale 0 for the current input, so it needs the W byte retuned at the same time.
// Filed as "Defect 5" in benchmarks/BENCHMARK.md and deliberately NOT changed
// here, so this row keeps measuring a non-degenerate payload.
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
    int rows = 10, cols = 2560, n_blocks = cols / 256;
    unsigned char *W = malloc(rows * n_blocks * 144);
    long *x = malloc(cols * 8), *y = malloc(rows * 8);
    memset(W, 0x97, rows * n_blocks * 144);
    for (int i = 0; i < cols; i++) x[i] = 128;
    matvec_q4k(W, x, rows, cols, y);
    printf("%ld\n", y[0]);
    free(W); free(x); free(y);
    return 0;
}
