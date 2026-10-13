// C equivalent: q4k_matmul
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define Q8_SCALE 128
int f16_to_q8(int f16) {
    int sign = (f16 / 32768) * 32768;
    int exp = (f16 - sign) / 1024;
    int mant = f16 - sign - exp * 1024;
    if (exp == 0) { if (mant == 0) return 0; return mant * Q8_SCALE / 1048576; }
    if (exp == 31) return 0;
    int base = 1024 + mant;
    int shift = exp - 15;
    if (shift >= 0) return base * (1 << shift) * Q8_SCALE / 1024;
    else return base * Q8_SCALE / 1024 / (1 << (-shift));
}
void dequant_q4k(unsigned char *W, long *out) {
    int scale_q8 = f16_to_q8(W[0] + W[1] * 256);
    for (int qi = 0; qi < 256; qi++) {
        int sub_q8 = W[2 + qi / 16];
        int byte_val = W[18 + qi / 2];
        int nibble = (qi % 2 == 0) ? (byte_val % 16) : (byte_val / 16);
        out[qi] = (long)(scale_q8 * sub_q8 * (nibble - 8) / Q8_SCALE);
    }
}
int main() {
    unsigned char W[256];
    memset(W, 0, 256);
    W[0] = 0; W[1] = 60;
    for (int i = 0; i < 16; i++) W[2 + i] = 1;
    for (int i = 0; i < 128; i++) W[18 + i] = 0x97;
    long x[256], dequant[256];
    for (int i = 0; i < 256; i++) x[i] = 128;
    dequant_q4k(W, dequant);
    long sum = 0;
    for (int j = 0; j < 256; j++) sum += dequant[j] * x[j] / Q8_SCALE;
    printf("result=%ld\n", sum);
    printf("%s\n", sum == 0 ? "PASS" : "FAIL (expected 0)");
    return 0;
}
