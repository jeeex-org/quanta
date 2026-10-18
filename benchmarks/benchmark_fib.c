// C equivalent: fib
#include <stdio.h>
long fib(int n) {
    if (n <= 1) return n;
    long a = 0, b = 1;
    for (long i = 2; i <= n; i++) { long t = a + b; a = b; b = t; }
    return b;
}
int main() {
    printf("fib(40)=%ld\n", fib(40));
    return 0;
}
