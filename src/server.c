#include "utils.h"
#include <arpa/inet.h>
#include <errno.h>
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct receive_slot {
    struct packet packet;
    int occupied;
};

static int reply(int fd, const struct sockaddr_in *peer, uint64_t id,
                 uint8_t type, uint32_t sequence)
{
    struct packet packet = {.type = type, .transfer_id = id, .sequence = sequence};
    return send_packet(fd, &packet, peer);
}

static void report_error(int fd, const struct sockaddr_in *peer, uint64_t id,
                         const char *message)
{
    struct packet packet = {.type = PACKET_ERROR, .transfer_id = id};
    packet.length = (uint16_t)strlen(message);
    memcpy(packet.payload, message, packet.length);
    (void)send_packet(fd, &packet, peer);
    fprintf(stderr, "%s\n", message);
}

static int data_ack(int fd, const struct sockaddr_in *peer, uint64_t id,
                    uint32_t sequence, uint32_t base, struct receive_slot *slots, int sack)
{
    if (!sack) return reply(fd, peer, id, PACKET_ACK, sequence);
    struct packet ack = {.type = PACKET_SACK, .transfer_id = id,
                         .sequence = sequence, .length = 8};
    /* Repeating buffered coverage repairs ACK loss without resending DATA.
     * base was drained before this call, so its bit must remain clear. */
    uint32_t bitmap = 0;
    for (unsigned int bit = 0; bit < WINDOW_SIZE; ++bit)
        if ((uint64_t)base + bit <= UINT32_MAX && slots[(base + bit) % WINDOW_SIZE].occupied)
            bitmap |= UINT32_C(1) << bit;
    put_u32(ack.payload, base); put_u32(ack.payload + 4, bitmap);
    return send_packet(fd, &ack, peer);
}

int main(int argc, char *argv[])
{
    uint16_t port;
    if (argc != 3) {
        fprintf(stderr, "Usage: %s <port> <output-file>\n", argv[0]);
        return EXIT_FAILURE;
    }
    if (parse_port(argv[1], &port) != 0) {
        fprintf(stderr, "Invalid port: %s\n", argv[1]);
        return EXIT_FAILURE;
    }
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        perror("socket");
        return EXIT_FAILURE;
    }
    struct sockaddr_in local = {0}, client = {0};
    local.sin_family = AF_INET;
    local.sin_port = htons(port);
    local.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(fd, (struct sockaddr *)&local, sizeof(local)) != 0) {
        perror("bind");
        close(fd);
        return EXIT_FAILURE;
    }
    printf("Listening on UDP port %u...\n", port);
    fflush(stdout);

    FILE *progress = NULL;
    const char *log_path = getenv("RUDP_PROGRESS_LOG");
    if (log_path && *log_path && !(progress = fopen(log_path, "wx"))) {
        perror("create progress log"); close(fd); return EXIT_FAILURE;
    }
    int sack = 0;
    FILE *output = NULL;
    char *temporary_path = NULL;
    int active = 0, complete = 0, temporary_created = 0, status = EXIT_FAILURE;
    uint64_t id = 0, expected_size = 0, written = 0;
    uint64_t packet_count = 0, duplicates = 0, reordered = 0;
    uint32_t expected_crc = 0, running_crc = UINT32_MAX, base = 0;
    uint64_t last_activity = monotonic_ms(), finish_deadline = 0, started = 0;
    struct receive_slot slots[WINDOW_SIZE] = {0};
    for (;;) {
        uint64_t now = monotonic_ms();
        if (complete && now >= finish_deadline) {
            status = EXIT_SUCCESS;
            break;
        }
        if (!complete && now - last_activity >= SESSION_TIMEOUT_MS) {
            fprintf(stderr, "Timed out %s; transfer incomplete.\n",
                    active ? "during transfer" : "waiting for START");
            break;
        }
        struct packet packet;
        struct sockaddr_in peer;
        int result = receive_packet(fd, &packet, &peer, 100);
        if (result < 0) {
            perror("receive packet");
            break;
        }
        if (!result)
            continue;
        if (!active) {
            if ((packet.type != PACKET_START && packet.type != PACKET_START_SACK) || packet.sequence != 0 ||
                packet.length != START_PAYLOAD_SIZE)
                continue;
            sack = packet.type == PACKET_START_SACK;
            expected_size = get_u64(packet.payload);
            packet_count = expected_size / PAYLOAD_SIZE + (expected_size % PAYLOAD_SIZE != 0);
            if (packet_count > UINT32_MAX) {
                report_error(fd, &peer, packet.transfer_id, "File exceeds protocol sequence range");
                continue;
            }
            expected_crc = get_u32(packet.payload + 8);
            client = peer;
            id = packet.transfer_id;
            size_t path_size = strlen(argv[2]) + sizeof(".part.XXXXXX");
            temporary_path = malloc(path_size);
            if (!temporary_path) {
                report_error(fd, &client, id, "Cannot allocate output path");
                break;
            }
            snprintf(temporary_path, path_size, "%s.part.XXXXXX", argv[2]);
            int output_fd = mkstemp(temporary_path);
            if (output_fd < 0) {
                report_error(fd, &client, id, "Cannot create temporary output");
                break;
            }
            temporary_created = 1;
            output = fdopen(output_fd, "wb");
            if (!output) {
                close(output_fd);
                report_error(fd, &client, id, "Cannot open temporary output");
                break;
            }
            active = 1;
            started = last_activity = monotonic_ms();
            if (reply(fd, &client, id, sack ? PACKET_START_SACK_ACK : PACKET_START_ACK, 0) != 0) {
                perror("send START_ACK");
                break;
            }
            continue;
        }
        if (!same_peer(&peer, &client) || packet.transfer_id != id)
            continue;
        if (packet.type == (sack ? PACKET_START_SACK : PACKET_START) && packet.sequence == 0 &&
            packet.length == START_PAYLOAD_SIZE &&
            get_u64(packet.payload) == expected_size &&
            get_u32(packet.payload + 8) == expected_crc) {
            if (reply(fd, &client, id, sack ? PACKET_START_SACK_ACK : PACKET_START_ACK, 0) != 0)
                break;
            continue;
        }
        if (packet.type == PACKET_DATA && packet.sequence < packet_count) {
            uint64_t remaining = expected_size - (uint64_t)packet.sequence * PAYLOAD_SIZE;
            uint16_t expected_length = (uint16_t)(remaining < PAYLOAD_SIZE ? remaining : PAYLOAD_SIZE);
            if (packet.length != expected_length)
                continue;
            if (packet.sequence < base) {
                ++duplicates;
                if (data_ack(fd, &client, id, packet.sequence, base, slots, sack) != 0)
                    break;
                continue;
            }
            if (complete || packet.sequence - base >= WINDOW_SIZE)
                continue;
            struct receive_slot *slot = &slots[packet.sequence % WINDOW_SIZE];
            if (!slot->occupied) {
                slot->packet = packet;
                slot->occupied = 1;
                if (packet.sequence != base) {
                    ++reordered;
                    progress_event(progress, "out_of_order", id, packet.sequence, base, 0, "buffered");
                    progress_event(progress, "gap_detected", id, packet.sequence, base, 0, "missing_base");
                } else {
                    int buffered = 0;
                    for (unsigned int i = 0; i < WINDOW_SIZE; ++i)
                        if (i != base % WINDOW_SIZE && slots[i].occupied) buffered = 1;
                    if (buffered) progress_event(progress, "hole_filled", id, packet.sequence, base, 0, "ordered_drain");
                }
            } else {
                ++duplicates;
            }
            /* ACK only after the in-order prefix has been written successfully. */
            while (base < packet_count && slots[base % WINDOW_SIZE].occupied) {
                struct receive_slot *head = &slots[base % WINDOW_SIZE];
                if (fwrite(head->packet.payload, 1, head->packet.length, output) != head->packet.length) {
                    report_error(fd, &client, id, "Cannot write output");
                    goto cleanup;
                }
                running_crc = crc32_update(running_crc, head->packet.payload, head->packet.length);
                written += head->packet.length;
                head->occupied = 0;
                ++base;
            }
            last_activity = monotonic_ms();
            if (data_ack(fd, &client, id, packet.sequence, base, slots, sack) != 0)
                break;
            continue;
        }
        if (packet.type != PACKET_FIN || packet.length != 0 || packet.sequence != packet_count)
            continue;
        if (!complete) {
            if (base != packet_count)
                continue;
            if (written != expected_size || (running_crc ^ UINT32_MAX) != expected_crc) {
                report_error(fd, &client, id, "File size or CRC32 mismatch");
                break;
            }
            /* Publish only a verified complete file; a failed session must
             * leave any previous destination intact. Rename is not fsync. */
            int close_result = fclose(output);
            output = NULL;
            if (close_result != 0 || rename(temporary_path, argv[2]) != 0) {
                report_error(fd, &client, id, "Cannot finalize output");
                break;
            }
            complete = 1;
            finish_deadline = monotonic_ms() + FIN_LINGER_MS;
            printf("Transfer complete: bytes=%" PRIu64 " crc32=%08" PRIx32
                   " duplicates=%" PRIu64 " out_of_order=%" PRIu64 " seconds=%.3f\n",
                   written, expected_crc, duplicates, reordered,
                   (double)(monotonic_ms() - started) / 1000.0);
            fflush(stdout);
        }
        /* Re-ACK duplicate FINs if FIN_ACK was lost; never rewrite the file. */
        if (reply(fd, &client, id, PACKET_FIN_ACK, (uint32_t)packet_count) != 0)
            break;
    }
cleanup:
    if (output)
        fclose(output);
    if (temporary_path) {
        if (temporary_created && !complete)
            unlink(temporary_path);
        free(temporary_path);
    }
    if (progress) fclose(progress);
    close(fd);
    return status;
}
