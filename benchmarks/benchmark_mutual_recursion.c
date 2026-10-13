// C twin: same NON-tail mutual recursion (the +1 after the call blocks sibling-call elimination),
// noinline + volatile base case so gcc cannot derive the closed form.
#include <stdio.h>
static volatile long zero = 0;
__attribute__((noinline)) static long is_even(long n);
__attribute__((noinline)) static long is_odd(long n) { if (n == zero) return 0; return is_even(n - 1) + 1; }
__attribute__((noinline)) static long is_even(long n) { if (n == zero) return 1; return is_odd(n - 1) + 1; }
int main(void) {
    long s = 0;
    for (long outer = 0; outer < 20; outer++)
        for (long i = 0; i < 2000; i++) s += is_even(i);
    printf("%ld\n", s);
    return 0;
}
