// C Recursion benchmark
#include <stdio.h>

long fact(long n) {
    if (n <= 1) return 1;
    return n * fact(n - 1);
}

int main() {
    long sum = 0;
    for (long i = 0; i < 1000; i++) {
        sum += fact(10);
    }
    printf("%ld\n", sum);
    return 0;
}