// C equivalent: match
#include <stdio.h>
const char* classify(int n) {
    if (n == 0) return "zero";
    if (n > 0) return "positive";
    return "negative";
}
int main() {
    int vals[] = {-3, 0, 5, -1, 10};
    for (long i = 0; i < 5; i++) {
        printf("classify(%d)=%s\n", vals[i], classify(vals[i]));
    }
    return 0;
}
