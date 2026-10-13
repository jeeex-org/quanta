// C Basic arithmetic benchmark
#include <stdio.h>
int main() {
    long sum = 0;
    for (int i = 0; i < 20000000; i++) sum += i * 7 - i / 3 + i % 5;
    printf("%ld\n", sum);
    return 0;
}