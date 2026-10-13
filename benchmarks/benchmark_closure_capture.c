// C twin: indirect call reading a captured value from a struct env.
#include <stdio.h>
typedef struct { long y; long (*f)(struct env *, long); } closure;
struct env { long y; };
static long add_y(struct env *e, long x) { return x + e->y; }
int main(void) {
    struct env e = { 7 };
    closure c = { 7, add_y };
    long s = 0;
    for (long i = 0; i < 1000000; i++) s += c.f(&e, i);
    printf("%ld\n", s);
    return 0;
}
