#include "utils.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <string.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define PROTOCOL_MAGIC UINT32_C(0x52554450)
#define PROTOCOL_VERSION 1u

void put_u32(unsigned char *out, uint32_t value)
{
    for (unsigned int i = 0; i < 4; ++i)
        out[i] = (unsigned char)(value >> (24u - 8u * i));
}

uint32_t get_u32(const unsigned char *in)
{
    uint32_t value = 0;
    for (unsigned int i = 0; i < 4; ++i)
        value = (value << 8) | in[i];
    return value;
}

void put_u64(unsigned char *out, uint64_t value)
{
    put_u32(out, (uint32_t)(value >> 32));
    put_u32(out + 4, (uint32_t)value);
}

uint64_t get_u64(const unsigned char *in)
{
    return ((uint64_t)get_u32(in) << 32) | get_u32(in + 4);
}

/* IEEE CRC-32, initial state UINT32_MAX, final XOR UINT32_MAX. */
uint32_t crc32_update(uint32_t state, const unsigned char *data, size_t size)
{
    for (size_t i = 0; i < size; ++i) {
        state ^= data[i];
        for (unsigned int bit = 0; bit < 8; ++bit)
            state = (state >> 1) ^ (UINT32_C(0xedb88320) & (0u - (state & 1u)));
    }
    return state;
}

size_t packet_encode(unsigned char *wire, const struct packet *packet)
{
    if (packet->length > PAYLOAD_SIZE)
        return 0;
    put_u32(wire, PROTOCOL_MAGIC);
    wire[4] = PROTOCOL_VERSION;
    wire[5] = packet->type;
    wire[6] = (unsigned char)(packet->length >> 8);
    wire[7] = (unsigned char)packet->length;
    put_u64(wire + 8, packet->transfer_id);
    put_u32(wire + 16, packet->sequence);
    memset(wire + 20, 0, 4);
    memcpy(wire + HEADER_SIZE, packet->payload, packet->length);
    size_t size = HEADER_SIZE + packet->length;
    put_u32(wire + 20, crc32_update(UINT32_MAX, wire, size) ^ UINT32_MAX);
    return size;
}

int packet_decode(struct packet *packet, const unsigned char *wire, size_t size)
{
    if (size < HEADER_SIZE || size > MAX_PACKET_SIZE ||
        get_u32(wire) != PROTOCOL_MAGIC || wire[4] != PROTOCOL_VERSION ||
        wire[5] < PACKET_START || wire[5] > PACKET_SACK)
        return -1;
    uint16_t length = (uint16_t)((uint16_t)wire[6] << 8 | wire[7]);
    if (length > PAYLOAD_SIZE || size != HEADER_SIZE + length)
        return -1;
    unsigned char copy[MAX_PACKET_SIZE];
    memcpy(copy, wire, size);
    memset(copy + 20, 0, 4);
    if ((crc32_update(UINT32_MAX, copy, size) ^ UINT32_MAX) != get_u32(wire + 20))
        return -1;
    packet->type = wire[5];
    packet->transfer_id = get_u64(wire + 8);
    packet->sequence = get_u32(wire + 16);
    packet->length = length;
    memcpy(packet->payload, wire + HEADER_SIZE, length);
    return 0;
}

int parse_port(const char *text, uint16_t *port)
{
    unsigned long value = 0;
    if (*text == '\0')
        return -1;
    for (; *text; ++text) {
        if (*text < '0' || *text > '9')
            return -1;
        value = value * 10 + (unsigned int)(*text - '0');
        if (value > UINT16_MAX)
            return -1;
    }
    if (!value)
        return -1;
    *port = (uint16_t)value;
    return 0;
}

uint64_t monotonic_ns(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
        perror("clock_gettime");
        _exit(1);
    }
    return (uint64_t)now.tv_sec * UINT64_C(1000000000) + (uint64_t)now.tv_nsec;
}

uint64_t monotonic_ms(void)
{
    return monotonic_ns() / UINT64_C(1000000);
}

int random_transfer_id(uint64_t *id)
{
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd < 0)
        return -1;
    size_t offset = 0;
    while (offset < sizeof(*id)) {
        ssize_t count = read(fd, (unsigned char *)id + offset, sizeof(*id) - offset);
        if (count < 0 && errno == EINTR)
            continue;
        if (count <= 0) {
            close(fd);
            return -1;
        }
        offset += (size_t)count;
    }
    return close(fd);
}

int file_metadata(FILE *file, uint64_t *size, uint32_t *checksum)
{
    unsigned char buffer[16384];
    uint32_t state = UINT32_MAX;
    *size = 0;
    size_t count;
    while ((count = fread(buffer, 1, sizeof(buffer), file)) > 0) {
        *size += count;
        state = crc32_update(state, buffer, count);
    }
    if (ferror(file) || fseeko(file, 0, SEEK_SET) != 0)
        return -1;
    *checksum = state ^ UINT32_MAX;
    return 0;
}

int same_peer(const struct sockaddr_in *a, const struct sockaddr_in *b)
{
    return a->sin_family == b->sin_family && a->sin_port == b->sin_port &&
           a->sin_addr.s_addr == b->sin_addr.s_addr;
}

int receive_packet(int fd, struct packet *packet, struct sockaddr_in *peer,
                   unsigned int timeout_ms)
{
    uint64_t deadline = monotonic_ms() + timeout_ms;
    struct pollfd item = {.fd = fd, .events = POLLIN};
    int ready;
    do {
        uint64_t now = monotonic_ms();
        int remaining = now >= deadline ? 0 : (int)(deadline - now);
        ready = poll(&item, 1, remaining);
    } while (ready < 0 && errno == EINTR);
    if (ready <= 0)
        return ready;
    unsigned char wire[MAX_PACKET_SIZE + 1];
    socklen_t length = sizeof(*peer);
    ssize_t size = recvfrom(fd, wire, sizeof(wire), 0, (struct sockaddr *)peer, &length);
    if (size < 0)
        return errno == EINTR ? 0 : -1;
    return packet_decode(packet, wire, (size_t)size) == 0 ? 1 : 0;
}

int send_packet(int fd, const struct packet *packet, const struct sockaddr_in *peer)
{
    unsigned char wire[MAX_PACKET_SIZE];
    size_t size = packet_encode(wire, packet);
    if (!size)
        return -1;
    ssize_t sent;
    do {
        sent = sendto(fd, wire, size, 0, (const struct sockaddr *)peer, sizeof(*peer));
    } while (sent < 0 && errno == EINTR);
    return sent == (ssize_t)size ? 0 : -1;
}

/* Stable numeric event schema, shared by both endpoints. */
void progress_event(FILE *log, const char *event, uint64_t id, uint32_t sequence,
                    uint32_t base, double value, const char *reason)
{
    if (!log) return;
    if (fprintf(log, "{\"event\":\"%s\",\"monotonic_ns\":%llu,\"transfer_id\":\"%016llx\",\"sequence\":%u,\"base\":%u,\"value\":%.3f,\"reason\":\"%s\"}\n",
                event, (unsigned long long)monotonic_ns(), (unsigned long long)id,
                sequence, base, value, reason) < 0 || fflush(log) != 0) {
        perror("write progress log");
        _exit(1);
    }
}
int option_enabled(const char *name)
{
    const char *value = getenv(name);
    return !value || strcmp(value, "0") != 0;
}
