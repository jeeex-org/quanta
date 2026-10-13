// C equivalent: enum
#include <stdio.h>
enum Color { Red, Green, Blue };
const char* color_name(enum Color c) {
    if (c == Red) return "Red";
    if (c == Green) return "Green";
    return "Blue";
}
int main() {
    printf("%s\n", color_name(Green));
    return 0;
}
