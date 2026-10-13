// C equivalent: loop_sum. The bound depends on argc, which the compiler can never know:
// with a literal bound gcc computes Gauss's sum at compile time and deletes the loop
// (a fictional baseline). Run with no extra args, n == 1000000 exactly as in the .quanta twin.
#include <stdio.h>
int main(int argc, char **argv) {
    (void)argv;
    long n = 1000000 + (argc - 1);
    long sum = 0;
    for (long i = 1; i <= n; i++) sum += i;
    printf("sum=%ld\n", sum);
    return 0;
}
