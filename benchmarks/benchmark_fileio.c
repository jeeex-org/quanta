// C File I/O benchmark
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdlib.h>
int main() {
    int N = 10000;
    int BUF_SIZE = 1024;
    unsigned char *buf = malloc(BUF_SIZE);
    for (long i = 0; i < BUF_SIZE; i++) buf[i] = i % 256;
    int fd = open("/tmp/bench_io.dat", O_CREAT | O_WRONLY | O_TRUNC, 0644);
    for (long i = 0; i < N; i++) write(fd, buf, BUF_SIZE);
    close(fd);
    int fd2 = open("/tmp/bench_io.dat", O_RDONLY);
    long sum = 0;
    for (long i = 0; i < N; i++) {
        read(fd2, buf, BUF_SIZE);
        for (long j = 0; j < BUF_SIZE; j++) sum += buf[j];
    }
    close(fd2);
    printf("%ld\n", sum);
    free(buf);
    return 0;
}