// C equivalent: file_io
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
int main() {
    int fd = open("/etc/hostname", O_RDONLY);
    if (fd < 0) { printf("open failed\n"); return 1; }
    char buf[256];
    int n = read(fd, buf, 256);
    printf("read %d bytes: %.*s\n", n, n, buf);
    close(fd);
    return 0;
}
