#include "utils.h"
#include <arpa/inet.h>
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct send_slot {
    struct packet packet;
    uint64_t sent_at;
    unsigned int retries;
    int acknowledged;
};

struct statistics {
    uint64_t data_sends;
    uint64_t data_retries;
    uint64_t control_retries;
};

/* START and FIN are stop-and-wait exchanges; DATA uses Selective Repeat. */
static int exchange(int fd, const struct sockaddr_in *server,
                    const struct packet *request, uint8_t expected_type,
                    struct statistics *stats)
{
    for (unsigned int attempt = 0; attempt <= MAX_RETRIES; ++attempt) {
        if (send_packet(fd, request, server) != 0) {
            perror("send control packet");
            return -1;
        }
        if (attempt)
            ++stats->control_retries;
        uint64_t deadline = monotonic_ms() + RETRY_TIMEOUT_MS;
        for (;;) {
            uint64_t now = monotonic_ms();
            if (now >= deadline)
                break;
            struct packet reply;
            struct sockaddr_in peer;
            unsigned int remaining = (unsigned int)(deadline - now);
            int result = receive_packet(fd, &reply, &peer, remaining);
            if (result < 0) {
                perror("receive control ACK");
                return -1;
            }
            if (!result || !same_peer(&peer, server) ||
                reply.transfer_id != request->transfer_id)
                continue;
            if (reply.type == PACKET_ERROR) {
                fprintf(stderr, "Server rejected transfer: %.*s\n",
                        (int)reply.length, reply.payload);
                return -1;
            }
            if (reply.type == expected_type && reply.sequence == request->sequence &&
                reply.length == 0)
                return 0;
        }
    }
    fprintf(stderr, "No acknowledgement for control packet %u after %u retries.\n",
            request->type, MAX_RETRIES);
    return -1;
}

static int send_file(int fd, FILE *file, const struct sockaddr_in *server,
                     uint64_t id, uint32_t packet_count, uint64_t file_size,
                     struct statistics *stats)
{
    struct send_slot slots[WINDOW_SIZE] = {0};
    uint32_t base = 0, next = 0;
    while (base < packet_count) {
        while (next < packet_count && next - base < WINDOW_SIZE) {
            struct send_slot *slot = &slots[next % WINDOW_SIZE];
            memset(slot, 0, sizeof(*slot));
            slot->packet.type = PACKET_DATA;
            slot->packet.transfer_id = id;
            slot->packet.sequence = next;
            uint64_t remaining = file_size - (uint64_t)next * PAYLOAD_SIZE;
            slot->packet.length = (uint16_t)(remaining < PAYLOAD_SIZE ? remaining : PAYLOAD_SIZE);
            if (fread(slot->packet.payload, 1, slot->packet.length, file) != slot->packet.length) {
                fprintf(stderr, "Input file changed or could not be read.\n");
                return -1;
            }
            if (send_packet(fd, &slot->packet, server) != 0) {
                perror("send DATA");
                return -1;
            }
            slot->sent_at = monotonic_ms();
            ++stats->data_sends;
            ++next;
        }

        /* Poll only until the oldest outstanding packet's deadline. */
        uint64_t now = monotonic_ms();
        unsigned int wait_ms = RETRY_TIMEOUT_MS;
        for (uint32_t sequence = base; sequence < next; ++sequence) {
            struct send_slot *slot = &slots[sequence % WINDOW_SIZE];
            if (slot->acknowledged)
                continue;
            uint64_t elapsed = now - slot->sent_at;
            if (elapsed >= RETRY_TIMEOUT_MS) {
                if (slot->retries >= MAX_RETRIES) {
                    fprintf(stderr, "Retry limit reached for DATA %" PRIu32 ".\n", sequence);
                    return -1;
                }
                if (send_packet(fd, &slot->packet, server) != 0) {
                    perror("retransmit DATA");
                    return -1;
                }
                slot->sent_at = monotonic_ms();
                ++slot->retries;
                ++stats->data_sends;
                ++stats->data_retries;
                elapsed = 0;
            }
            unsigned int left = RETRY_TIMEOUT_MS - (unsigned int)elapsed;
            if (left < wait_ms)
                wait_ms = left;
        }
        struct packet ack;
        struct sockaddr_in peer;
        int result = receive_packet(fd, &ack, &peer, wait_ms);
        if (result < 0) {
            perror("receive DATA ACK");
            return -1;
        }
        if (result == 1 && same_peer(&peer, server) && ack.transfer_id == id) {
            if (ack.type == PACKET_ERROR) {
                fprintf(stderr, "Server rejected transfer: %.*s\n", (int)ack.length, ack.payload);
                return -1;
            }
            if (ack.type == PACKET_ACK && ack.length == 0 &&
                ack.sequence >= base && ack.sequence < next)
                slots[ack.sequence % WINDOW_SIZE].acknowledged = 1;
        }
        while (base < next && slots[base % WINDOW_SIZE].acknowledged)
            ++base;
    }
    /* Detect append/read failures after the metadata pass. CRC catches other changes. */
    if (fgetc(file) != EOF || ferror(file)) {
        fprintf(stderr, "Input file changed or could not be read.\n");
        return -1;
    }
    return 0;
}

int main(int argc, char *argv[])
{
    uint16_t port;
    if (argc != 4) {
        fprintf(stderr, "Usage: %s <server-ip> <port> <file>\n", argv[0]);
        return EXIT_FAILURE;
    }
    if (parse_port(argv[2], &port) != 0) {
        fprintf(stderr, "Invalid port: %s\n", argv[2]);
        return EXIT_FAILURE;
    }
    struct sockaddr_in server = {0};
    server.sin_family = AF_INET;
    server.sin_port = htons(port);
    if (inet_pton(AF_INET, argv[1], &server.sin_addr) != 1) {
        fprintf(stderr, "Invalid IPv4 address: %s\n", argv[1]);
        return EXIT_FAILURE;
    }
    FILE *file = fopen(argv[3], "rb");
    if (!file) {
        perror("open input");
        return EXIT_FAILURE;
    }
    int status = EXIT_FAILURE;
    int fd = -1;
    uint64_t size, id;
    uint32_t checksum;
    if (file_metadata(file, &size, &checksum) != 0) {
        perror("read input metadata");
        goto cleanup;
    }
    uint64_t count = size / PAYLOAD_SIZE + (size % PAYLOAD_SIZE != 0);
    if (count > UINT32_MAX) {
        fprintf(stderr, "File exceeds protocol sequence range.\n");
        goto cleanup;
    }
    if (random_transfer_id(&id) != 0) {
        perror("generate transfer ID");
        goto cleanup;
    }
    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        perror("socket");
        goto cleanup;
    }
    struct statistics stats = {0};
    uint64_t start = monotonic_ms();
    struct packet control = {.type = PACKET_START, .transfer_id = id,
                             .length = START_PAYLOAD_SIZE};
    put_u64(control.payload, size);
    put_u32(control.payload + 8, checksum);
    if (exchange(fd, &server, &control, PACKET_START_ACK, &stats) != 0 ||
        send_file(fd, file, &server, id, (uint32_t)count, size, &stats) != 0)
        goto cleanup;
    control.type = PACKET_FIN;
    control.sequence = (uint32_t)count;
    control.length = 0;
    if (exchange(fd, &server, &control, PACKET_FIN_ACK, &stats) != 0)
        goto cleanup;
    double seconds = (double)(monotonic_ms() - start) / 1000.0;
    printf("Transfer complete: bytes=%" PRIu64 " crc32=%08" PRIx32
           " packets=%" PRIu64 " data_sends=%" PRIu64 " retransmits=%" PRIu64
           " control_retransmits=%" PRIu64 " seconds=%.3f goodput_mbps=%.3f\n",
           size, checksum, count, stats.data_sends, stats.data_retries,
           stats.control_retries, seconds, seconds > 0 ? (double)size * 8 / seconds / 1e6 : 0);
    status = EXIT_SUCCESS;
cleanup:
    if (fd >= 0)
        close(fd);
    fclose(file);
    return status;
}
