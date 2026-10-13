// C twin: indirect call through a function pointer. The pointer is volatile and the callee
// noinline, otherwise gcc devirtualizes + inlines it and deletes the loop.
#include <stdio.h>
__attribute__((noinline)) static long inc(long x) { return x + 1; }
static long (*volatile f)(long) = inc;
int main(void) {
    long s = 0;
    for (long i = 0; i < 1000000; i++) s += f(i);
    printf("%ld\n", s);
    return 0;
}
