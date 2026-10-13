// C twin: same, magnitude chosen to fit int64 (see the .quanta twin's header).
#include <stdio.h>
long fib(int n) {
    if (n <= 1) return n;
    long a = 0, b = 1;
    for (int i = 2; i <= n; i++) { long t = a + b; a = b; b = t; }
    return b;
}
int main() {
    long sum = 0;
    for (int i = 0; i < 10000; i++) sum += fib(60);
    printf("sum=%ld\n", sum);
    return 0;
}
