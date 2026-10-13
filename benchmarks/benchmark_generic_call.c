// C twin: the monomorphic equivalent, noinline so the calls cannot be folded away.
#include <stdio.h>
__attribute__((noinline)) static long id(long x) { return x; }
__attribute__((noinline)) static long addv(long a, long b) { return a + b; }
int main(void) {
    long s = 0;
    for (long i = 0; i < 1000000; i++) s = addv(id(s), i);
    printf("%ld\n", s);
    return 0;
}
