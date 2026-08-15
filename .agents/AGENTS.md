# Workspace Rules

- Do not perform Git operations (commits, pushes, tags, etc.) unless explicitly instructed by the user.

## MicroPython ESP32 SSL & Networking Rules

- **Avoid SSL in Background Threads / No Concurrent Threads**: Avoid using background threads for HTTPS/SSL connections. Furthermore, on this firmware and hardware, DO NOT run ANY background threads (even lightweight ones like an LED pulsar) concurrently during active HTTPS/SSL connections. The stack space allocated for threads reduces available system (RTOS) heap, causing `MBEDTLS_ERR_X509_ALLOC_FAILED` during SSL handshakes.
- **Clean Socket Shutdown (Avoid RST)**: Always read and discard the entire response headers and body from HTTP requests (both GET and POST) before closing sockets. Closing a socket with unread data in the receive buffer causes a TCP Reset (RST) which aborts serverless lambdas (e.g. on Vercel) and prevents database writes.
- **Avoid LwIP TIME_WAIT State via Passive Close**: Low-level `setsockopt` for `SO_LINGER` is NOT implemented in this MicroPython firmware build and triggers a warning. To prevent client sockets from entering the 2-minute `TIME_WAIT` state and consuming system heap, always request the server to close the connection by sending the `Connection: close` header in HTTP requests. Once the response is fully read (EOF reached), perform a passive close by closing the socket. Always explicitly close both the wrapped SSL socket and the underlying base socket, then set their references to `None` and run `gc.collect()`.
- **Throttle Connection Frequency**: Throttle duplicate or consecutive config synchronization and status requests. Enforce a minimum interval (e.g. 60 seconds) between requests to prevent system heap exhaustion from back-to-back SSL handshakes.
- **Timeout Preservation on SSL**: Socket timeouts (`s.settimeout(5)`) are lost when wrapping a socket in SSL. Always re-apply the timeout directly to the wrapped SSL socket wrapper inside a try-catch block.
- **Heap GC before SSL Handshake**: mbedTLS handshakes require large contiguous blocks of heap RAM (15-20KB). Always call `gc.collect()` immediately before `ssl.wrap_socket(s)` to avoid memory allocation failures (`ENOMEM`/`MBEDTLS_ERR_X509_ALLOC_FAILED`).
- **Telemetry Duplication Control**: Never send duplicate telemetry packets or start/complete cycle events in rapid succession. Keep telemetry events lightweight and ensure they are only triggered on final phase completions, explicit user pauses, reactions, or cancellations.


