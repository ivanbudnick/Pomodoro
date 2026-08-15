# Workspace Rules

- Do not perform Git operations (commits, pushes, tags, etc.) unless explicitly instructed by the user.

## MicroPython ESP32 SSL & Networking Rules

- **Thread Stack Size for SSL**: Any background thread that wraps sockets in SSL (`ssl.wrap_socket`) or makes HTTPS requests must be allocated a stack size of at least `20480` bytes (20KB) via `_thread.stack_size(20480)` before starting, and reset to `0` immediately after. Smaller stack sizes (like 8KB) will cause a silent stack overflow and freeze the thread.
- **Clean Socket Shutdown (Avoid RST)**: Always read and discard the entire response headers and body from HTTP requests (both GET and POST) before closing sockets. Closing a socket with unread data in the receive buffer causes a TCP Reset (RST) which aborts serverless lambdas (e.g. on Vercel) and prevents database writes.
- **Timeout Preservation on SSL**: Socket timeouts (`s.settimeout(5)`) are lost when wrapping a socket in SSL. Always re-apply the timeout directly to the wrapped SSL socket wrapper inside a try-catch block.
- **Heap GC before SSL Handshake**: mbedTLS handshakes require large contiguous blocks of heap RAM (15-20KB). Always call `gc.collect()` immediately before `ssl.wrap_socket(s)` to avoid memory allocation failures (`ENOMEM`/`MBEDTLS_ERR_X509_ALLOC_FAILED`).
- **Telemetry Duplication Control**: Never send duplicate telemetry packets or start/complete cycle events in rapid succession. Keep telemetry events lightweight and ensure they are only triggered on final phase completions, explicit user pauses, reactions, or cancellations.
