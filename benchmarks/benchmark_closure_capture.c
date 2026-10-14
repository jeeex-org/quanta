// C twin: indirect call reading a captured value from a struct env.
//
// Twin repair (0.0.238 prep), TWO defects, both of which made the row measure
// nothing:
//
// 1. `struct env` used to be declared INSIDE the function-pointer parameter
//    list — `long (*f)(struct env *, long)` — which makes that `struct env` a
//    distinct, prototype-scoped type, so `add_y`'s pointer was INCOMPATIBLE
//    with the field type and gcc -O2 REJECTED the file ("initialization ... from
//    incompatible pointer type"). bench.sh never reached the C side because the
//    stale known-fail marker on the Quanta twin short-circuited the row first.
//    Declaring `struct env` once, before the typedef, fixes that.
// 2. With defect 1 fixed, gcc -O2 devirtualises the struct-held function
//    pointer and folds the loop to its closed form: gate 1 measured ZERO jumps
//    inside main, i.e. the twin ran no loop at all. This is guard 3 of
//    benchmarks/BENCHMARK.md ("devirtualisation is invisible to guard 1") — the
//    same artifact that once produced a bogus "0.005 s" C baseline. Making the
//    closure object `volatile` forces gcc to reload the pointer each iteration,
//    so the indirect call is real and the loop survives.
#include <stdio.h>
struct env { long y; };
typedef struct { long y; long (*f)(struct env *, long); } closure;
static long add_y(struct env *e, long x) { return x + e->y; }
int main(void) {
    struct env e = { 7 };
    volatile closure c;          // volatile: the call cannot be devirtualised
    c.y = 7;
    c.f = add_y;
    long s = 0;
    for (long i = 0; i < 1000000; i++) s += c.f(&e, i);
    printf("%ld\n", s);
    return 0;
}
