// C equivalent: mem_ops
#include <stdio.h>
#include <stdlib.h>
int main() {
    long *arr = malloc(10000 * 8);
    for (int i = 0; i < 10000; i++) arr[i] = i * 2;
    long sum = 0;
    for (int i = 0; i < 10000; i++) sum += arr[i];
    printf("sum=%ld\n", sum);
    free(arr);
    return 0;
}
