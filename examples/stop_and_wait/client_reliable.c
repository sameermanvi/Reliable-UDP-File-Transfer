#define _POSIX_C_SOURCE 200809L

#include <arpa/inet.h>
#include <errno.h>
#include <inttypes.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#include "protocol.h"

static int wait_for_ack(int sock, uint32_t expected_seq,
                        const struct sockaddr_in *server)
{
    fd_set readfds;
    FD_ZERO(&readfds);
    FD_SET(sock, &readfds);

    struct timeval timeout;
    timeout.tv_sec = ACK_TIMEOUT_MS / 1000;
    timeout.tv_usec = (ACK_TIMEOUT_MS % 1000) * 1000;

    int ready = select(sock + 1, &readfds, NULL, NULL, &timeout);

    if (ready < 0) {
        if (errno == EINTR)
            return 1;

        perror("select");
        return -1;
    }

    if (ready == 0)
        return 1;

    Packet ack;
    struct sockaddr_in from;
    socklen_t from_len = sizeof(from);
    memset(&ack, 0, sizeof(ack));

    ssize_t n = recvfrom(sock, &ack, sizeof(ack), 0,
                         (struct sockaddr *)&from, &from_len);

    if (n < 0) {
        if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)
            return 1;

        perror("recvfrom");
        return -1;
    }

    if (n < (ssize_t)PACKET_HEADER_SIZE)
        return 1;

    if (from.sin_addr.s_addr != server->sin_addr.s_addr ||
        from.sin_port != server->sin_port)
        return 1;

    if (ack.magic == PACKET_MAGIC &&
        ack.type == PACKET_ACK &&
        ack.seq == expected_seq)
        return 0;

    return 1;
}

static int send_packet_with_retry(int sock, const Packet *packet,
                                  size_t packet_size,
                                  const struct sockaddr_in *server)
{
    for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
        ssize_t sent = sendto(sock, packet, packet_size, 0,
                              (const struct sockaddr *)server,
                              sizeof(*server));

        if (sent < 0) {
            perror("sendto");
            return -1;
        }

        if ((size_t)sent != packet_size) {
            fprintf(stderr, "Incomplete UDP packet send.\n");
            return -1;
        }

        if (wait_for_ack(sock, packet->seq, server) == 0)
            return 0;
    }

    return -1;
}

int main(int argc, char *argv[])
{
    if (argc != 3) {
        fprintf(stderr, "Usage: %s <server_ip> <file_path>\n", argv[0]);
        return EXIT_FAILURE;
    }

    FILE *file = fopen(argv[2], "rb");
    if (file == NULL) {
        perror("Cannot open file");
        return EXIT_FAILURE;
    }

    if (fseek(file, 0, SEEK_END) != 0) {
        perror("fseek");
        fclose(file);
        return EXIT_FAILURE;
    }

    long file_size = ftell(file);
    if (file_size < 0) {
        perror("ftell");
        fclose(file);
        return EXIT_FAILURE;
    }

    rewind(file);

    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        perror("socket");
        fclose(file);
        return EXIT_FAILURE;
    }

    struct sockaddr_in server;
    memset(&server, 0, sizeof(server));
    server.sin_family = AF_INET;
    server.sin_port = htons(UDP_PORT);

    if (inet_pton(AF_INET, argv[1], &server.sin_addr) != 1) {
        fprintf(stderr, "Invalid server IPv4 address: %s\n", argv[1]);
        close(sock);
        fclose(file);
        return EXIT_FAILURE;
    }

    Packet packet;
    memset(&packet, 0, sizeof(packet));
    packet.magic = PACKET_MAGIC;
    packet.type = PACKET_START;
    packet.seq = 0;
    packet.total_size = (uint64_t)file_size;

    printf("Reliable UDP File Transfer Client\n");
    printf("File: %s (%" PRIu64 " bytes)\n",
           argv[2], packet.total_size);

    if (send_packet_with_retry(sock, &packet, PACKET_HEADER_SIZE,
                               &server) != 0) {
        fprintf(stderr, "Failed to start transfer.\n");
        close(sock);
        fclose(file);
        return EXIT_FAILURE;
    }

    uint32_t seq = 1;
    uint64_t total_sent = 0;

    while (total_sent < (uint64_t)file_size) {
        memset(&packet, 0, sizeof(packet));
        packet.magic = PACKET_MAGIC;
        packet.type = PACKET_DATA;
        packet.seq = seq;
        packet.total_size = (uint64_t)file_size;

        size_t bytes_read = fread(packet.data, 1, DATA_SIZE, file);
        if (bytes_read == 0) {
            if (ferror(file))
                perror("fread");
            else
                fprintf(stderr, "Unexpected end of file.\n");

            close(sock);
            fclose(file);
            return EXIT_FAILURE;
        }

        packet.data_len = (uint32_t)bytes_read;
        packet.checksum = payload_checksum(packet.data, bytes_read);

        size_t packet_size = PACKET_HEADER_SIZE + bytes_read;

        if (send_packet_with_retry(sock, &packet, packet_size, &server) != 0) {
            fprintf(stderr, "Transfer failed at sequence %" PRIu32 "\n", seq);
            close(sock);
            fclose(file);
            return EXIT_FAILURE;
        }

        total_sent += bytes_read;
        printf("Sent packet %" PRIu32
               " (%zu bytes; %" PRIu64 "/%" PRIu64 ")\n",
               seq, bytes_read, total_sent, (uint64_t)file_size);
        seq++;
    }

    if (fclose(file) != 0) {
        perror("fclose");
        close(sock);
        return EXIT_FAILURE;
    }

    close(sock);
    printf("File transfer completed successfully.\n");
    return EXIT_SUCCESS;
}

