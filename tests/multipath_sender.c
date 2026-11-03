/* Exercise the real sender's DSCP selection without requiring an SDN switch. */
#define main client_main
#define setsockopt record_setsockopt
#define send_packet record_send_packet
#include "../src/client.c"
#undef main
#undef setsockopt
#undef send_packet
#include <assert.h>

static int current_tos, observed_tos;

int record_setsockopt(int fd, int level, int option, const void *value, socklen_t length)
{
    (void)fd;
    assert(level == IPPROTO_IP && option == IP_TOS && length == sizeof(int));
    current_tos = *(const int *)value;
    return 0;
}

int record_send_packet(int fd, const struct packet *packet, const struct sockaddr_in *peer)
{
    (void)fd; (void)packet; (void)peer;
    observed_tos = current_tos;
    return 0;
}

int main(void)
{
    struct packet packet = {0};
    struct sockaddr_in peer = {0};
    for (unsigned int sequence = 0; sequence < 16; ++sequence) {
        packet.sequence = sequence;
        for (int attempt = 0; attempt < 2; ++attempt) {
            assert(send_data(0, &packet, &peer, 0, 1, 3, 1) == 0);
            assert(observed_tos == ((sequence % 4 < 3 ? 8 : 16) << 2));
            assert(current_tos == 0); /* Control traffic must not inherit DATA's mark. */
        }
    }
    assert(send_data(0, &packet, &peer, 0, 0, 1, 1) == 0);
    assert(observed_tos == 0);
    assert(send_data(0, &packet, &peer, 0, 1, 0, 1) == -1);
    return 0;
}
