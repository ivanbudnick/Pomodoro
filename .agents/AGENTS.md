# Workspace Rules

- Do not perform Git operations (commits, pushes, tags, etc.) unless explicitly instructed by the user.

## MicroPython ESP32 SSL & Networking Rules

- **Avoid SSL in Background Threads**: Avoid using background threads for HTTPS/SSL connections. Thread stacks (e.g. 20KB) allocated from the system heap leave mbedTLS without enough memory, causing `ENOMEM` during the handshake. Perform HTTPS requests synchronously during phase transitions and pause the main thread while utilizing hardware PWM for a user-facing sync animation (e.g. a gentle Cyan LED glow).
- **Clean Socket Shutdown (Avoid RST)**: Always read and discard the entire response headers and body from HTTP requests (both GET and POST) before closing sockets. Closing a socket with unread data in the receive buffer causes a TCP Reset (RST) which aborts serverless lambdas (e.g. on Vercel) and prevents database writes.
- **Avoid LwIP TIME_WAIT State**: Configure the `SO_LINGER` option to `0` (l_onoff=1, l_linger=0) on sockets before connecting to avoid the 2-minute `TIME_WAIT` state, releasing system heap and sockets immediately upon closure.
- **Throttle Connection Frequency**: Throttle duplicate or consecutive config synchronization and status requests. Enforce a minimum interval (e.g. 60 seconds) between requests to prevent system heap exhaustion from back-to-back SSL handshakes.
- **Timeout Preservation on SSL**: Socket timeouts (`s.settimeout(5)`) are lost when wrapping a socket in SSL. Always re-apply the timeout directly to the wrapped SSL socket wrapper inside a try-catch block.
- **Heap GC before SSL Handshake**: mbedTLS handshakes require large contiguous blocks of heap RAM (15-20KB). Always call `gc.collect()` immediately before `ssl.wrap_socket(s)` to avoid memory allocation failures (`ENOMEM`/`MBEDTLS_ERR_X509_ALLOC_FAILED`).
- **Telemetry Duplication Control**: Never send duplicate telemetry packets or start/complete cycle events in rapid succession. Keep telemetry events lightweight and ensure they are only triggered on final phase completions, explicit user pauses, reactions, or cancellations.

