// C Division by constant benchmark
#include <stdio.h>
int main() {
    long sum = 0;
    for (int i = 0; i < 10000000; i++) sum += i / 128 * 3 + i / 64 - i / 32;
    printf("%ld\n", sum);
    return 0;
}