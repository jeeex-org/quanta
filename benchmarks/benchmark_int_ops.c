// C equivalent: int_ops
#include <stdio.h>
int main() {
    long x = 10, y = 20;
    printf("sum=%ld diff=%ld prod=%ld div=%ld mod=%ld\n", x+y, y-x, x*y, y/x, y%x);
    return 0;
}
