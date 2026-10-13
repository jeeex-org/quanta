// C twin: two function pointers, volatile so the calls stay indirect.
#include <stdio.h>
__attribute__((noinline)) static long add1(long x) { return x + 1; }
__attribute__((noinline)) static long sub1(long x) { return x - 1; }
static long (*volatile f)(long) = add1;
static long (*volatile g)(long) = sub1;
int main(void) {
    long s = 0;
    for (long i = 0; i < 1000000; i++) { s += f(i); s += g(i); }
    printf("%ld\n", s);
    return 0;
}
