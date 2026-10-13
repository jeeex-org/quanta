// C twin: same 8-argument function, noinline so the >6-arg call actually happens.
#include <stdio.h>
__attribute__((noinline)) static long s(long a, long b, long c, long d, long e, long f, long g, long h) {
    return a + b + c + d + e + f + g + h;
}
int main(void) {
    long t = 0;
    for (long i = 0; i < 1000000; i++) t += s(i, 1, 2, 3, 4, 5, 6, 7);
    printf("%ld\n", t);
    return 0;
}
