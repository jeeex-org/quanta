// C Memory operations benchmark
#include <stdio.h>
#include <stdlib.h>
int main() {
    int N = 500000;
    long *arr = malloc(N * 8);
    for (int i = 0; i < N; i++) arr[i] = (long)i * 7;
    long sum = 0;
    for (int i = 0; i < N; i++) sum += arr[i];
    unsigned char *b = (unsigned char*)arr;
    for (int i = 0; i < N; i++) b[i] = (unsigned char)i;
    long sum8 = 0;
    for (int i = 0; i < N; i++) sum8 += b[i];
    printf("%ld %ld\n", sum, sum8);
    free(arr);
    return 0;
}