// C heavy int loop
#include <stdio.h>
int main() {
    long sum = 0;
    for (long i = 0; i < 200000000; i++) sum += i * 7 / 3;
    printf("sum=%ld\n", sum);
    return 0;
}
