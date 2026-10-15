// C twin of benchmarks/benchmark_regpressure.quanta — same computation, same
// output. gcc keeps the sixteen live temporaries in registers; Quanta must spill
// and reload them (13-register pool), which is what the row measures.
#include <stdio.h>

int main() {
    const long N = 2000000;
    long sum = 0;
    for (long i = 0; i < N; i++) {
        long t0 = i + 1, t1 = i + 2, t2 = i + 3, t3 = i + 4;
        long t4 = i + 5, t5 = i + 6, t6 = i + 7, t7 = i + 8;
        long t8 = i + 9, t9 = i + 10, t10 = i + 11, t11 = i + 12;
        long t12 = i + 13, t13 = i + 14, t14 = i + 15, t15 = i + 16;
        sum = sum + t15 + t14 + t13 + t12 + t11 + t10 + t9 + t8;
        sum = sum + t7 + t6 + t5 + t4 + t3 + t2 + t1 + t0;
    }
    printf("sum=%ld\n", sum);
    return 0;
}
