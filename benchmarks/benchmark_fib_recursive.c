// C equivalent: recursive fib(30). Kept in lockstep with benchmark_fib_recursive.quanta.
#include <stdio.h>
long fib(long n){ return n<2 ? n : fib(n-1)+fib(n-2); }
int main(void){ printf("%ld", fib(30)); return 0; }
