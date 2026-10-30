#include <arpa/inet.h>
#include <errno.h>
#include <inttypes.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#include "protocol.h"

#define OUTPUT_FILE "received_file.bin"
#define FINAL_ACK_WAIT_SECONDS 3

static int send_ack(int sock, const Packet *ack,
                    const struct sockaddr_in *client,
                    socklen_t client_len)
{
    ssize_t sent = sendto(sock, ack, PACKET_HEADER_SIZE, 0,
                          (const struct sockaddr *)client, client_len);

    if (sent != (ssize_t)PACKET_HEADER_SIZE) {
        perror("sendto ACK");
        return -1;
    }

    return 0;
}

int main(void)
{
    int server_socket = socket(AF_INET, SOCK_DGRAM, 0);

    if (server_socket < 0) {
        perror("socket");
        return EXIT_FAILURE;
    }

    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(UDP_PORT);
    server_addr.sin_addr.s_addr = htonl(INADDR_ANY);

    if (bind(server_socket, (struct sockaddr *)&server_addr,
             sizeof(server_addr)) < 0) {
        perror("bind");
        close(server_socket);
        return EXIT_FAILURE;
    }

    printf("Reliable UDP File Transfer Server\n");
    printf("Listening on UDP port %d...\n", UDP_PORT);
    fflush(stdout);

    FILE *file = NULL;
    Packet packet;
    Packet ack;

    struct sockaddr_in transfer_client;
    memset(&transfer_client, 0, sizeof(transfer_client));

    uint64_t expected_size = 0;
    uint64_t received_size = 0;
    uint32_t expected_seq = 1;
    uint32_t last_ack = 0;
    uint32_t final_seq = 0;

    unsigned char final_data[DATA_SIZE];
    uint32_t final_data_len = 0;
    uint32_t final_checksum = 0;

    int started = 0;
    int success = 0;

    for (;;) {
        memset(&packet, 0, sizeof(packet));

        struct sockaddr_in client_addr;
        memset(&client_addr, 0, sizeof(client_addr));
        socklen_t client_len = sizeof(client_addr);

        ssize_t n = recvfrom(server_socket, &packet, sizeof(packet), 0,
                             (struct sockaddr *)&client_addr, &client_len);

        if (n < 0) {
            if (errno == EINTR)
                continue;

            perror("recvfrom");
            break;
        }

        if (n < (ssize_t)PACKET_HEADER_SIZE ||
            packet.magic != PACKET_MAGIC)
            continue;

        if (!started) {
            if (packet.type != PACKET_START ||
                packet.seq != 0 ||
                n != (ssize_t)PACKET_HEADER_SIZE)
                continue;

            expected_size = packet.total_size;
            transfer_client = client_addr;

            file = fopen(OUTPUT_FILE, "wb");
            if (file == NULL) {
                perror("fopen");
                break;
            }

            started = 1;

            printf("Client connected: %s\n",
                   inet_ntoa(client_addr.sin_addr));
            printf("Expected file size: %" PRIu64 " bytes\n",
                   expected_size);

            if (expected_size == 0) {
                if (fflush(file) != 0) {
                    perror("fflush");
                    break;
                }

                if (fclose(file) != 0) {
                    file = NULL;
                    perror("fclose");
                    break;
                }

                file = NULL;
                success = 1;
                printf("Empty file received successfully.\n");
            }

            memset(&ack, 0, sizeof(ack));
            ack.magic = PACKET_MAGIC;
            ack.type = PACKET_ACK;
            ack.seq = 0;

            if (send_ack(server_socket, &ack, &client_addr,
                         client_len) != 0) {
                success = 0;
                break;
            }

                        if (expected_size == 0) {
                struct timeval timeout;
                timeout.tv_sec = FINAL_ACK_WAIT_SECONDS;
                timeout.tv_usec = 0;

                if (setsockopt(server_socket, SOL_SOCKET, SO_RCVTIMEO,
                               &timeout, sizeof(timeout)) < 0) {
                    perror("setsockopt");
                    success = 0;
                    break;
                }

                for (;;) {
                    Packet retry_packet;
                    struct sockaddr_in retry_client;
                    socklen_t retry_client_len = sizeof(retry_client);

                    ssize_t retry_n = recvfrom(
                        server_socket, &retry_packet,
                        sizeof(retry_packet), 0,
                        (struct sockaddr *)&retry_client,
                        &retry_client_len
                    );

                    if (retry_n < 0) {
                        if (errno == EAGAIN || errno == EWOULDBLOCK)
                            break;

                        if (errno == EINTR)
                            continue;

                        perror("recvfrom empty-file retry");
                        success = 0;
                        break;
                    }

                    if (retry_client.sin_addr.s_addr !=
                            transfer_client.sin_addr.s_addr ||
                        retry_client.sin_port != transfer_client.sin_port)
                        continue;

                    if (retry_n != (ssize_t)PACKET_HEADER_SIZE ||
                        retry_packet.magic != PACKET_MAGIC ||
                        retry_packet.type != PACKET_START ||
                        retry_packet.seq != 0 ||
                        retry_packet.total_size != 0)
                        continue;

                    memset(&ack, 0, sizeof(ack));
                    ack.magic = PACKET_MAGIC;
                    ack.type = PACKET_ACK;
                    ack.seq = 0;

                    if (send_ack(server_socket, &ack, &retry_client,
                                 retry_client_len) != 0) {
                        success = 0;
                        break;
                    }

                    printf("Re-acknowledged empty-file START packet.\n");
                }

                break;
            }

            continue;
        }

        if (client_addr.sin_addr.s_addr !=
                transfer_client.sin_addr.s_addr ||
            client_addr.sin_port != transfer_client.sin_port)
            continue;

        if (packet.type == PACKET_START &&
            packet.seq == 0 &&
            n == (ssize_t)PACKET_HEADER_SIZE &&
            packet.total_size == expected_size) {
            memset(&ack, 0, sizeof(ack));
            ack.magic = PACKET_MAGIC;
            ack.type = PACKET_ACK;
            ack.seq = 0;

            if (send_ack(server_socket, &ack, &client_addr,
                         client_len) != 0)
                break;

            continue;
        }

        if (packet.type != PACKET_DATA ||
            packet.data_len == 0 ||
            packet.data_len > DATA_SIZE ||
            n != (ssize_t)(PACKET_HEADER_SIZE + packet.data_len))
            continue;

        if (payload_checksum(packet.data, packet.data_len) !=
            packet.checksum) {
            fprintf(stderr, "Checksum error in packet %" PRIu32 "\n",
                    packet.seq);
            continue;
        }

        if (packet.seq == expected_seq) {
            if (received_size + packet.data_len > expected_size) {
                fprintf(stderr, "Unexpected file size.\n");
                break;
            }

            if (received_size + packet.data_len == expected_size) {
                /*
                 * Save the final packet so a retransmission can be
                 * validated after the file has been closed.
                 */
                final_seq = packet.seq;
                final_data_len = packet.data_len;
                final_checksum = packet.checksum;
                memcpy(final_data, packet.data, packet.data_len);

                if (fwrite(packet.data, 1, packet.data_len, file) !=
                    packet.data_len) {
                    perror("fwrite");
                    break;
                }

                received_size += packet.data_len;
                last_ack = packet.seq;
                expected_seq++;

                if (fflush(file) != 0) {
                    perror("fflush");
                    break;
                }

                if (fclose(file) != 0) {
                    file = NULL;
                    perror("fclose");
                    break;
                }

                file = NULL;
                success = 1;

                printf("Received final packet %" PRIu32
                       " (%" PRIu32 " bytes)\n",
                       final_seq, final_data_len);

                printf("File received successfully: %s\n", OUTPUT_FILE);
            } else {
                size_t written = fwrite(
                    packet.data, 1, packet.data_len, file
                );

                if (written != packet.data_len) {
                    perror("fwrite");
                    break;
                }

                received_size += packet.data_len;
                last_ack = packet.seq;
                expected_seq++;

                printf("Received packet %" PRIu32
                       " (%" PRIu32 " bytes; %" PRIu64 "/%" PRIu64 ")\n",
                       packet.seq, packet.data_len,
                       received_size, expected_size);
            }
        } else if (packet.seq < expected_seq) {
            /*
             * Duplicate packet: don't write it twice.
             * Re-ACK the most recent in-order packet.
             */
        } else {
            /* Out-of-order packet: acknowledge the last in-order packet. */
        }

        memset(&ack, 0, sizeof(ack));
        ack.magic = PACKET_MAGIC;
        ack.type = PACKET_ACK;
        ack.seq = last_ack;

        if (success && received_size == expected_size) {
            ack.seq = final_seq;
        }

        if (send_ack(server_socket, &ack, &client_addr,
                     client_len) != 0) {
            success = 0;
            break;
        }

        if (success && received_size == expected_size) {
            struct timeval timeout;
            timeout.tv_sec = FINAL_ACK_WAIT_SECONDS;
            timeout.tv_usec = 0;

            if (setsockopt(server_socket, SOL_SOCKET, SO_RCVTIMEO,
                           &timeout, sizeof(timeout)) < 0) {
                perror("setsockopt");
                success = 0;
                break;
            }

            for (;;) {
                Packet retry_packet;
                struct sockaddr_in retry_client;
                socklen_t retry_client_len = sizeof(retry_client);

                ssize_t retry_n = recvfrom(
                    server_socket, &retry_packet, sizeof(retry_packet), 0,
                    (struct sockaddr *)&retry_client, &retry_client_len
                );

                if (retry_n < 0) {
                    if (errno == EAGAIN || errno == EWOULDBLOCK)
                        break;

                    if (errno == EINTR)
                        continue;

                    perror("recvfrom final retry");
                    success = 0;
                    break;
                }

                if (retry_client.sin_addr.s_addr !=
                        transfer_client.sin_addr.s_addr ||
                    retry_client.sin_port != transfer_client.sin_port)
                    continue;

                if (retry_n < (ssize_t)PACKET_HEADER_SIZE ||
                    retry_packet.magic != PACKET_MAGIC ||
                    retry_packet.type != PACKET_DATA ||
                    retry_packet.seq != final_seq ||
                    retry_packet.data_len != final_data_len ||
                    retry_packet.checksum != final_checksum ||
                    retry_n != (ssize_t)(PACKET_HEADER_SIZE +
                                         retry_packet.data_len) ||
                    memcmp(retry_packet.data, final_data,
                           final_data_len) != 0)
                    continue;

                memset(&ack, 0, sizeof(ack));
                ack.magic = PACKET_MAGIC;
                ack.type = PACKET_ACK;
                ack.seq = final_seq;

                if (send_ack(server_socket, &ack, &retry_client,
                             retry_client_len) != 0) {
                    success = 0;
                    break;
                }

                printf("Re-acknowledged final packet %" PRIu32 "\n",
                       final_seq);
            }

            break;
        }
    }

    if (file != NULL) {
        if (fclose(file) != 0) {
            perror("fclose");
            success = 0;
        }
    }

    close(server_socket);
    printf("Server stopped.\n");

    return success ? EXIT_SUCCESS : EXIT_FAILURE;
}
