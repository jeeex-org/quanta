// C heavy division
#include <stdio.h>
int main() {
    long sum = 0;
    for (long i = 0; i < 100000000; i++) sum += i / 128 * 3;
    printf("sum=%ld\n", sum);
    return 0;
}
