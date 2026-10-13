// C equivalent: float_ops. Prints f64 BIT PATTERNS to match Quanta's `print` on floats.
#include <stdio.h>
int main() {
    double a = 3.0, b = 2.0;
    double r_add = a + b, r_sub = b - a, r_mul = a * b, r_div = b / a;
    printf("fadd=%lld fsub=%lld fmul=%lld fdiv=%lld\n",
        *(long long *)&r_add, *(long long *)&r_sub, *(long long *)&r_mul, *(long long *)&r_div);
    return 0;
}
