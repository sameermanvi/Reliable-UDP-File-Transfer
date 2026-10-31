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
    unsigned int timeout_ms;
    unsigned int gap_reports;
    int fast_sent;
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
                     struct statistics *stats, FILE *progress)
{
    struct send_slot slots[WINDOW_SIZE] = {0};
    uint32_t base = 0, next = 0, recovery_end = 0, backoff_end = 0;
    const char *rto_mode = getenv("RUDP_RTO");
    int adaptive = rto_mode ? strcmp(rto_mode, "adaptive") == 0 : option_enabled("RUDP_ADAPTIVE_RTO");
    int congestion = option_enabled("RUDP_CC");
    double srtt = 0, variance = 0, rto = RETRY_TIMEOUT_MS;
    double cwnd = congestion ? 4 : WINDOW_SIZE, threshold = 16;
    progress_event(progress, "cwnd_change", id, 0, 0, cwnd, "initial");
    while (base < packet_count) {
        while (next < packet_count && next - base < WINDOW_SIZE && next - base < (uint32_t)cwnd) {
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
            slot->timeout_ms = (unsigned int)rto;
            progress_event(progress, "send", id, next, base, rto, "original");
            ++stats->data_sends;
            ++next;
        }

        /* Poll only until the oldest outstanding packet's deadline. */
        uint64_t now = monotonic_ms();
        unsigned int wait_ms = 2000;
        for (uint32_t sequence = base; sequence < next; ++sequence) {
            struct send_slot *slot = &slots[sequence % WINDOW_SIZE];
            if (slot->acknowledged)
                continue;
            uint64_t elapsed = now - slot->sent_at;
            if (elapsed >= slot->timeout_ms) {
                if (slot->retries >= MAX_RETRIES) {
                    fprintf(stderr, "Retry limit reached for DATA %" PRIu32 ".\n", sequence);
                    return -1;
                }
                if (send_packet(fd, &slot->packet, server) != 0) {
                    perror("retransmit DATA");
                    return -1;
                }
                progress_event(progress, "loss_detected", id, sequence, base, slot->timeout_ms, "timeout");
                if (congestion && (recovery_end == 0 || base >= recovery_end)) {
                    threshold = cwnd / 2 < 2 ? 2 : cwnd / 2;
                    cwnd = 1;
                    recovery_end = next;
                    progress_event(progress, "cwnd_change", id, sequence, base, cwnd, "timeout");
                }
                if (adaptive && (backoff_end == 0 || base >= backoff_end)) {
                    rto = rto < 1000 ? rto * 2 : 2000;
                    backoff_end = next;
                    progress_event(progress, "rto_update", id, sequence, base, rto, "timeout_backoff");
                }
                slot->sent_at = monotonic_ms();
                if (adaptive) slot->timeout_ms = slot->timeout_ms < 1000 ? slot->timeout_ms * 2 : 2000;
                progress_event(progress, "retransmit", id, sequence, base, slot->timeout_ms, "timeout");
                ++slot->retries;
                ++stats->data_sends;
                ++stats->data_retries;
                elapsed = 0;
            }
            unsigned int left = slot->timeout_ms - (unsigned int)elapsed;
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
            int sack = ack.type == PACKET_SACK && ack.length == 8 && option_enabled("RUDP_SACK");
            if (((ack.type == PACKET_ACK && ack.length == 0) || sack) &&
                ack.sequence < next) {
                uint32_t receiver_base = sack ? get_u32(ack.payload) : 0;
                uint32_t bitmap = sack ? get_u32(ack.payload + 4) : 0;
                int invalid_sack = receiver_base > next || (bitmap & 1u);
                for (unsigned int bit = 0; bit < WINDOW_SIZE; ++bit)
                    if ((bitmap & (UINT32_C(1) << bit)) && (uint64_t)receiver_base + bit >= next)
                        invalid_sack = 1;
                /* Echo must agree with cumulative/bitmap coverage. Reject the whole
                 * report before changing slots, RTT, cwnd, or gap evidence. */
                if (sack && ack.sequence >= receiver_base &&
                    (ack.sequence - receiver_base >= WINDOW_SIZE ||
                     !(bitmap & (UINT32_C(1) << (ack.sequence - receiver_base)))))
                    invalid_sack = 1;
                if (invalid_sack) {
                    progress_event(progress, "ack_rejected", id, ack.sequence, base, bitmap, "invalid_sack");
                    continue;
                }
                progress_event(progress, "ack_received", id, ack.sequence, base, bitmap, sack ? "sack" : "individual");
                for (uint32_t seq = base; seq < next; ++seq) {
                    struct send_slot *slot = &slots[seq % WINDOW_SIZE];
                    int covered = seq == ack.sequence || (sack && (seq < receiver_base ||
                        (seq >= receiver_base && seq - receiver_base < 32 &&
                         (bitmap & (UINT32_C(1) << (seq - receiver_base))))));
                    if (!covered || slot->acknowledged) continue;
                    slot->acknowledged = 1;
                    /* Karn: ambiguous retransmitted samples never train the estimator.
                     * Only the explicitly echoed sequence supplies an RTT sample. */
                    if (adaptive && !slot->retries && seq == ack.sequence) {
                        double sample = (double)(monotonic_ms() - slot->sent_at);
                        if (sample < 1) sample = 1;
                        if (!srtt) { srtt = sample; variance = sample / 2; }
                        else {
                            double error = srtt > sample ? srtt - sample : sample - srtt;
                            variance = .75 * variance + .25 * error;
                            srtt = .875 * srtt + .125 * sample;
                        }
                        rto = srtt + 4 * variance;
                        if (rto < 50) rto = 50;
                        if (rto > 2000) rto = 2000;
                        progress_event(progress, "rto_update", id, seq, base, rto, "rtt_sample");
                        progress_event(progress, "srtt_update", id, seq, base, srtt, "rtt_sample");
                    }
                    if (congestion) {
                        cwnd += cwnd < threshold ? 1 : 1 / cwnd;
                        if (cwnd > WINDOW_SIZE) cwnd = WINDOW_SIZE;
                        progress_event(progress, "cwnd_change", id, seq, base, cwnd, "new_ack");
                    }
                    /* Count distinct newly acknowledged later packets, not duplicate ACKs. */
                    for (uint32_t hole = base; hole < seq; ++hole)
                        if (!slots[hole % WINDOW_SIZE].acknowledged)
                            ++slots[hole % WINDOW_SIZE].gap_reports;
                }
                for (uint32_t seq = base; seq < next; ++seq) {
                    struct send_slot *slot = &slots[seq % WINDOW_SIZE];
                    if (slot->acknowledged || slot->fast_sent || slot->gap_reports < 3) continue;
                    if (slot->retries >= MAX_RETRIES) return -1;
                    if (send_packet(fd, &slot->packet, server) != 0) return -1;
                    slot->fast_sent = 1;
                    slot->sent_at = monotonic_ms();
                    ++slot->retries; ++stats->data_sends; ++stats->data_retries;
                    progress_event(progress, "loss_detected", id, seq, base, slot->gap_reports, "distinct_gap_acks");
                    progress_event(progress, "retransmit", id, seq, base, slot->timeout_ms, "fast_gap");
                    if (congestion && (recovery_end == 0 || base >= recovery_end)) {
                        threshold = cwnd / 2 < 2 ? 2 : cwnd / 2;
                        cwnd = threshold; recovery_end = next;
                        progress_event(progress, "cwnd_change", id, seq, base, cwnd, "fast_gap");
                    }
                }
            }
        }
        uint32_t previous_base = base;
        while (base < next && slots[base % WINDOW_SIZE].acknowledged)
            ++base;
        if (base != previous_base) progress_event(progress, "window_advance", id, base, base, cwnd, "contiguous_ack");
        if (progress && base != previous_base) {
            uint64_t bytes = (uint64_t)base * PAYLOAD_SIZE;
            if (bytes > file_size)
                bytes = file_size;
            if (fprintf(progress, "{\"event\":\"ack_progress\",\"monotonic_ns\":%" PRIu64
                        ",\"transfer_id\":\"%016" PRIx64 "\",\"base\":%" PRIu32 ",\"bytes\":%" PRIu64 "}\n",
                        monotonic_ns(), id, base, bytes) < 0 || fflush(progress) != 0) {
                perror("write progress log");
                return -1;
            }
        }
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
    const char *rto_mode = getenv("RUDP_RTO");
    if (rto_mode && strcmp(rto_mode, "fixed") && strcmp(rto_mode, "adaptive")) {
        fprintf(stderr, "RUDP_RTO must be fixed or adaptive.\n");
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
    FILE *progress = NULL;
    const char *progress_path = getenv("RUDP_PROGRESS_LOG");
    if (progress_path && *progress_path) {
        /* Never truncate an input or previous experiment by accident. */
        progress = fopen(progress_path, "wx");
        if (!progress) {
            perror("create progress log");
            goto cleanup;
        }
    }
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
    struct packet control = {.type = option_enabled("RUDP_SACK") ? PACKET_START_SACK : PACKET_START, .transfer_id = id,
                             .length = START_PAYLOAD_SIZE};
    put_u64(control.payload, size);
    put_u32(control.payload + 8, checksum);
    if (exchange(fd, &server, &control, option_enabled("RUDP_SACK") ? PACKET_START_SACK_ACK : PACKET_START_ACK, &stats) != 0 ||
        send_file(fd, file, &server, id, (uint32_t)count, size, &stats, progress) != 0)
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
    if (progress && fclose(progress) != 0) {
        perror("close progress log");
        status = EXIT_FAILURE;
    }
    if (fd >= 0)
        close(fd);
    fclose(file);
    return status;
}
