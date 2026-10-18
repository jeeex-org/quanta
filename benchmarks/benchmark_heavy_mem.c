// C heavy memory
#include <stdio.h>
#include <stdlib.h>
int main() {
    int N = 1000000;
    long *arr = malloc(N * 8);
    for (long i = 0; i < N; i++) arr[i] = i;
    long sum = 0;
    for (long i = 0; i < N; i++) sum += arr[i];
    printf("sum=%ld\n", sum);
    free(arr);
    return 0;
}
