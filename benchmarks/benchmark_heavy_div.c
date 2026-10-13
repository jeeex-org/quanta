// C heavy division
#include <stdio.h>
int main() {
    long sum = 0;
    for (int i = 0; i < 10000000; i++) sum += i / 128 * 3;
    printf("sum=%ld\n", sum);
    return 0;
}
