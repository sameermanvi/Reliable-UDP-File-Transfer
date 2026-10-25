CC = cc
CPPFLAGS += -D_POSIX_C_SOURCE=200809L
CFLAGS = -std=c11 -O2 -Wall -Wextra -Wpedantic

.PHONY: all clean test
all: client server

client: client.o utils.o
	$(CC) $(LDFLAGS) -o $@ $^ $(LDLIBS)

server: server.o utils.o
	$(CC) $(LDFLAGS) -o $@ $^ $(LDLIBS)

client.o server.o utils.o: packet.h utils.h

clean:
	$(RM) client server *.o

test: all
	python3 ../tests/test_protocol.py
