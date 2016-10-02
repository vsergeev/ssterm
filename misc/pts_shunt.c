/* pts_shunt
 * Create two pseudoterminal slaves and shunt data between them.
 *
 *  $ gcc pts_shunt.c -o pts_shunt
 *  $ ./pts_shunt
 *  /dev/pts/5 <=> /dev/pts/8
 *  ...^C
 *  $
 *
 */

#define _GNU_SOURCE
#include <stdlib.h>

#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>

int pts_open(void) {
    int fd;

    if ((fd = getpt()) < 0) {
        perror("getpt()");
        return -1;
    }
    if (grantpt(fd) < 0) {
        perror("grantpt()");
        return -1;
    }
    if (unlockpt(fd) < 0) {
        perror("unlockpt()");
        return -1;
    }

    return fd;
}

int pts_copy(int fd_from, int fd_to) {
    char buff[1024];
    int len;

    if ((len = read(fd_from, buff, sizeof(buff))) < 0) {
        perror("read()");
        return -1;
    }
    if (write(fd_to, buff, len) < len) {
        perror("write()");
        return -1;
    }

    return len;
}

int main(int argc, char *argv[]) {
    int pt1, pt2;
    char pt1_name[128], pt2_name[128];

    /* Open two pseudoterminals */
    if ((pt1 = pts_open()) < 0)
        return -1;
    if ((pt2 = pts_open()) < 0)
        return -1;

    /* Print pts names */
    ptsname_r(pt1, pt1_name, sizeof(pt1_name));
    ptsname_r(pt2, pt2_name, sizeof(pt2_name));
    printf("%s <=> %s\n", pt1_name, pt2_name);

    /* select() and read/write between them */
    while (1) {
        fd_set rfds;
        FD_ZERO(&rfds);
        FD_SET(pt1, &rfds);
        FD_SET(pt2, &rfds);

        if (select(pt2+1, &rfds, NULL, NULL, NULL) < 0) {
            perror("select");
            return -1;
        }

        if (FD_ISSET(pt1, &rfds)) {
            if (pts_copy(pt1, pt2) < 0)
                break;
        }
        if (FD_ISSET(pt2, &rfds)) {
            if (pts_copy(pt2, pt1) < 0)
                break;
        }
    }

    close(pt1);
    close(pt2);

    return 0;
}
