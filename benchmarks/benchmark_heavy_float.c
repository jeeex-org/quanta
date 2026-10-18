// C heavy float. Prints the f64 BIT PATTERN (Quanta's print emits raw bits).
#include <stdio.h>
int main() {
    double sum = 0;
    for (long i = 0; i < 10000000; i++) {
        double x = (double)i;
        sum += x * x;
    }
    printf("sum=%lld\n", *(long long *)&sum);
    return 0;
}
