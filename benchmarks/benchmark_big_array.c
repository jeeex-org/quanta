// C equivalent: big_array
#include <stdio.h>
#include <stdlib.h>
int main() {
    int SIZE = 100000;
    long *arr = malloc(SIZE * 8);
    for (long i = 0; i < SIZE; i++) arr[i] = i + 1;
    long sum = 0;
    for (long i = 0; i < SIZE; i++) sum += arr[i];
    long expected = (long)SIZE * (SIZE + 1) / 2;
    if (sum == expected) { printf("PASS sum=%ld\n", sum); return 0; }
    printf("FAIL sum=%ld expected=%ld\n", sum, expected);
    free(arr);
    return 1;
}
