#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

#define UDP_PORT 5000
#define DATA_SIZE 1024
#define MAX_RETRIES 10
#define ACK_TIMEOUT_MS 1000
#define PACKET_MAGIC 0x52554450u

#define PACKET_START 1
#define PACKET_DATA  2
#define PACKET_ACK   3

#pragma pack(push, 1)
typedef struct
{
    uint32_t magic;
    uint32_t type;
    uint32_t seq;
    uint32_t data_len;
    uint32_t checksum;
    uint64_t total_size;
    unsigned char data[DATA_SIZE];
} Packet;
#pragma pack(pop)

#define PACKET_HEADER_SIZE offsetof(Packet, data)

static inline uint32_t payload_checksum(
    const unsigned char *data, size_t len)
{
    uint32_t hash = 2166136261u;

    for (size_t i = 0; i < len; i++)
    {
        hash ^= data[i];
        hash *= 16777619u;
    }

    return hash;
}

#endif