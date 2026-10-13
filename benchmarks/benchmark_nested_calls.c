// C equivalent: nested_calls
#include <stdio.h>
long add(long a, long b) { return a + b; }
long mul(long a, long b) { return a * b; }
long compute(long x, long y, long z) { return add(mul(x, y), z); }
int main() {
    printf("compute(3,4,5)=%ld\n", compute(3, 4, 5));
    return 0;
}
