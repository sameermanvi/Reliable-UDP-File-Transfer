# Archived stop-and-wait baseline

This directory preserves the matching `client_reliable.c`, `protocol.h`, and
`server.c` from PR #3, main commit `438a7d56a00bc6dd15a2f7dacbb6d26d49dce20a`.
The source files are retained unchanged for reference and possible future
baseline experiments. This archive is excluded from the supported build/tests.

Its native packed-struct packet format, ACK behavior, and completion rules differ
from the Selective Repeat protocol in `src/`. Never mix the archived client or
server with the executables built by `make -C src`.

To compile the archived pair separately from the repository root:

```sh
cc -std=c11 -Wall -Wextra -Wpedantic examples/stop_and_wait/client_reliable.c -o /tmp/stop_wait_client
cc -std=c11 -Wall -Wextra -Wpedantic examples/stop_and_wait/server.c -o /tmp/stop_wait_server
```

Run the archived server from a disposable directory: it writes or overwrites
`received_file.bin` in its working directory and listens on fixed UDP port 5000.
Run `/tmp/stop_wait_client 127.0.0.1 /path/to/input.bin` in another terminal.
These commands document the original interface; the archived implementation has
not undergone the Selective Repeat fault suite or comparative benchmarking.

For the supported implementation, follow the root README and use `src/client`
and `src/server` with the same selected port.
