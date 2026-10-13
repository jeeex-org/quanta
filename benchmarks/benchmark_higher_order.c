// C twin: closure passed as a volatile function-pointer argument, invoked in a loop.
#include <stdio.h>
__attribute__((noinline)) static long dbl(long x) { return x * 2; }
static long (*volatile fp)(long) = dbl;
__attribute__((noinline)) static long apply(long (*f)(long), long x) { return f(x); }
int main(void) {
    long s = 0;
    for (long i = 0; i < 1000000; i++) s += apply(fp, i);
    printf("%ld\n", s);
    return 0;
}
