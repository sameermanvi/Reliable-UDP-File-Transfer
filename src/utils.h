#ifndef UTILS_H
#define UTILS_H

#include "packet.h"
#include <netinet/in.h>
#include <stdio.h>

int parse_port(const char *text, uint16_t *port);
uint64_t monotonic_ms(void);
uint64_t monotonic_ns(void);
int file_metadata(FILE *file, uint64_t *size, uint32_t *checksum);
/* Returns 1 for a valid packet, 0 for timeout/invalid input, -1 for I/O error. */
int receive_packet(int fd, struct packet *packet, struct sockaddr_in *peer,
                   unsigned int timeout_ms);
int send_packet(int fd, const struct packet *packet, const struct sockaddr_in *peer);
int same_peer(const struct sockaddr_in *a, const struct sockaddr_in *b);

#endif
