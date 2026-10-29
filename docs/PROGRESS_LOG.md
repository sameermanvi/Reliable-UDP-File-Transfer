# Measuring transfer progress

Set `RUDP_PROGRESS_LOG` on the client when measuring interrupted transfers:

```sh
RUDP_PROGRESS_LOG=/tmp/upload-progress.jsonl \
  ./src/client 127.0.0.1 9000 /path/to/input.bin
```

The log path must not exist. The client creates it exclusively to avoid
overwriting an input file or an earlier experiment. An open, write or close
failure makes the client return a nonzero status.

Each JSON line records an advance in the contiguous acknowledged prefix:

```json
{"event":"ack_progress","monotonic_ns":123456789000,"base":32,"bytes":32768}
```

`base` is the number of consecutive DATA chunks acknowledged from sequence zero.
`bytes` is the corresponding file prefix, capped at the declared file size.
An out-of-order ACK does not advance this value until the gap has been filled.
Each line is flushed immediately. Empty files produce an empty log.

Timestamps use POSIX `CLOCK_MONOTONIC` in nanoseconds. Compare them only with
the same clock on the same machine, for example Python
`time.clock_gettime_ns(time.CLOCK_MONOTONIC)`. They are not wall-clock timestamps.

Progress is not completion: FIN/FIN_ACK and the receiver's integrity check still
determine whether the transfer succeeds. Enabling logging does not change the
packet format, but file I/O can affect timing; enable it consistently in all
compared experiments.
