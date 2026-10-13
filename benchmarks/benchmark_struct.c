// C equivalent: struct
#include <stdio.h>
typedef struct { long width, height; } Rectangle;
long area(Rectangle r) { return r.width * r.height; }
int main() {
    Rectangle r = {10, 20};
    printf("area=%ld\n", area(r));
    return 0;
}
