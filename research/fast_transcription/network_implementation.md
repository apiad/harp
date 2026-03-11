# Network Implementation for Low-Latency Transcription

This document outlines implementation techniques for minimizing transcription latency in a Python background daemon like Harp, focusing on asynchronous processing, connection pooling, and optimized audio handling.

## 1. Asynchronous Chunked Uploads & Background Encoding

To minimize the "dead time" after a user stops recording, audio should be processed (encoded and potentially uploaded) *while* the recording is still in progress.

### Background Audio Encoding
Using a producer-consumer pattern allows encoding to happen concurrently with audio capture.

- **Library:** `sounddevice` (non-blocking callback) + `pylibopus`.
- **Mechanism:**
    1.  The `sounddevice` callback receives raw PCM frames (e.g., every 20ms).
    2.  The callback pushes these frames into a thread-safe `queue.Queue`.
    3.  A background worker thread pulls frames from the queue and encodes them using Opus.
    4.  The encoded Opus packets are appended to a byte buffer or fed into a streaming upload.

### Background Base64 Encoding
If using OpenRouter's `chat/completions` with `input_audio`, base64 encoding is required.
- **Optimization:** Base64 encoding is CPU-bound. For real-time processing, encode small chunks of Opus data into base64 strings as they are generated, rather than waiting for the final buffer.
- **Python Tip:** `base64.b64encode()` releases the GIL for larger inputs, but for small chunks, the overhead is negligible.

### Asynchronous Streaming Uploads
Both `httpx` and `aiohttp` support streaming the request body using generators.

```python
import httpx
import asyncio
import queue

class AudioStreamIterator:
    def __init__(self, q: queue.Queue):
        self.q = q
        self.active = True

    def stop(self):
        self.active = False

    def __iter__(self):
        while self.active or not self.q.empty():
            try:
                # Short timeout to check active status
                chunk = self.q.get(timeout=0.1)
                yield chunk
            except queue.Empty:
                continue

async def upload_streaming_audio(client: httpx.AsyncClient, stream_iterator: AudioStreamIterator):
    # This starts the POST request immediately. 
    # Data is sent as the iterator yields chunks.
    files = {'file': ('audio.opus', stream_iterator, 'audio/opus')}
    response = await client.post("https://api.example.com/v1/audio/transcriptions", files=files)
    return response
```

*Note: While many Whisper APIs (like OpenAI's) expect the full file, using Chunked Transfer Encoding (via a generator) allows the upload to happen in parallel with recording, meaning the server has the data almost immediately after the stream ends.*

---

## 2. Connection Pooling (OpenRouter / OpenAI)

Establishing a new connection (TCP + TLS handshake) can add 200ms–500ms of latency depending on the user's location.

### Best Practices with `httpx`
`httpx` is recommended because it supports **HTTP/2**, allowing multiple requests to share a single connection (multiplexing).

- **Reuse the Client:** Always use a single `httpx.AsyncClient` instance for the lifetime of the daemon.
- **Enable HTTP/2:** `httpx.AsyncClient(http2=True)`.
- **Configure Limits:** Increase keep-alive limits to ensure the connection stays warm between transcriptions.

```python
import httpx

# Global or class-level client
client = httpx.AsyncClient(
    http2=True,
    limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=300.0),
    timeout=httpx.Timeout(10.0, read=30.0)
)
```

### Best Practices with `aiohttp`
`aiohttp` is often faster for raw throughput and has a more mature connection pool.

- **TCPConnector:** Use a shared `TCPConnector` with `use_dns_cache=True`.
- **Keep-Alive:** `aiohttp` keeps connections alive by default when using a `ClientSession`.

---

## 3. Minimizing TLS and DNS Overhead

### DNS Optimization
- **Persistent IP:** If the API endpoint has a stable IP, you can skip DNS resolution entirely (though not recommended for production without a fallback).
- **aiodns:** For `aiohttp`, installing `aiodns` allows for faster, non-blocking DNS resolution.
- **OS-level Caching:** Ensure the host OS has a DNS cache (like `systemd-resolved` or `nscd`).

### TLS Handshake Reduction
- **TLS 1.3:** Ensure your environment (OpenSSL 1.1.1+) supports TLS 1.3, which reduces the handshake from two round-trips to one.
- **SSL Context Reuse:** Creating a new `ssl.SSLContext` is expensive. Reusing the client/session object handles this automatically.
- **Connection Warming:** Optionally, send a lightweight "ping" or HEAD request to the API host on daemon startup to establish the TLS session before the user actually records anything.

---

## 4. Overlapping Opus Encoding with API Requests

The goal is to have the audio ready for processing the instant the user releases the recording hotkey.

### Implementation Strategy
1.  **Fixed-size Frames:** Use 20ms frames (960 samples at 48kHz). This is the "sweet spot" for Opus latency and quality.
2.  **Continuous Encoding:** Encode each 20ms frame as it arrives in the background thread.
3.  **The "Pre-flight" Request:** If the API supports it, you can start the HTTP POST request as soon as recording *starts*, using the streaming generator mentioned in Section 1.
4.  **Finalizing:** When recording stops, the background thread pushes a "final" chunk (or EOF signal) to the queue, the generator closes, and the API call finishes the upload.

**Latency Gain:** This converts a sequential process (`Record -> Encode -> Upload -> Wait`) into a parallel one (`Record | Encode | Upload -> Wait`).

---

## 5. Optimized Python Libraries

### Audio I/O: `sounddevice`
- **Why:** Uses `CFFI` to interface with PortAudio. It is more modern and often more stable than `pyaudio` (which uses a C extension).
- **Latency Tip:** Set `blocksize` to the Opus frame size (e.g., 960) to avoid internal buffering and alignment issues.

### Audio Processing: `numpy`
- **Why:** `sounddevice` can return audio as `numpy` arrays. NumPy is highly optimized for the vector operations often needed before encoding (e.g., gain adjustment, float32 to int16 conversion).

### Audio Codec: `pylibopus`
- **Why:** It is a thin, fast wrapper around `libopus`. Opus is the industry standard for low-latency voice (used by Discord/WhatsApp).
- **Comparison:** Much faster than `pydub` (which wraps `ffmpeg` or `avconv` and has significant process-startup overhead).

### Concurrency: `asyncio` + `threading`
- **The Hybrid Approach:** Use `threading` for the audio callback and encoding worker (to avoid event loop jitter) and `asyncio` for the network I/O.
- **Interaction:** Use `loop.call_soon_threadsafe()` or `asyncio.Queue` to bridge the gap between the worker thread and the async network client.

---

## Summary Recommendation for Harp

| Component | Recommended Tool | Why? |
| :--- | :--- | :--- |
| **Audio Capture** | `sounddevice` | Low-latency CFFI callback, NumPy integration. |
| **Encoding** | `pylibopus` | Lowest latency voice codec, releases GIL. |
| **Network Client** | `httpx` | HTTP/2 support for connection multiplexing. |
| **Strategy** | **Streaming Upload** | Overlaps recording, encoding, and uploading. |
| **Data Format** | **Opus in Ogg/WebM** | Excellent compression-to-quality ratio. |
