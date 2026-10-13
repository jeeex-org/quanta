// C equivalent: float (float-preserving). Prints the f64 BIT PATTERN because Quanta's
// `print` emits the raw bits of a float value; this makes the row a bitwise check.
#include <stdio.h>
int main() {
    double sum = 0;
    for (int i = 0; i < 5000000; i++) {
        double x = (double)i;
        sum += x * x;
        sum += x / (x + 1);
    }
    printf("%lld\n", *(long long *)&sum);
    return 0;
}
