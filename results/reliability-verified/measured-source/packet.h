#ifndef PACKET_H
#define PACKET_H

#include <stddef.h>
#include <stdint.h>

/* Wire fields use network byte order; never send a native C struct. */
#define PAYLOAD_SIZE 1024u
#define HEADER_SIZE 24u
#define MAX_PACKET_SIZE (HEADER_SIZE + PAYLOAD_SIZE)
#define WINDOW_SIZE 32u
#define RETRY_TIMEOUT_MS 200u
#define MAX_RETRIES 30u
#define SESSION_TIMEOUT_MS 10000u
#define FIN_LINGER_MS ((MAX_RETRIES + 2u) * RETRY_TIMEOUT_MS)
#define START_PAYLOAD_SIZE 12u

enum packet_type {
    PACKET_START = 1, PACKET_START_ACK, PACKET_DATA, PACKET_ACK,
    PACKET_FIN, PACKET_FIN_ACK, PACKET_ERROR,
    PACKET_START_SACK, PACKET_START_SACK_ACK, PACKET_SACK
};

struct packet {
    uint8_t type;
    uint64_t transfer_id;
    uint32_t sequence;
    uint16_t length;
    unsigned char payload[PAYLOAD_SIZE];
};

size_t packet_encode(unsigned char *wire, const struct packet *packet);
int packet_decode(struct packet *packet, const unsigned char *wire, size_t size);
uint32_t crc32_update(uint32_t state, const unsigned char *data, size_t size);
void put_u32(unsigned char *out, uint32_t value);
uint32_t get_u32(const unsigned char *in);
void put_u64(unsigned char *out, uint64_t value);
uint64_t get_u64(const unsigned char *in);

#endif
