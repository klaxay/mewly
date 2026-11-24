# Architecture

```text
Microphone → capture/ → WebSocket → server.py → transcribe/
                                                    ↓
Browser viewer ← WebSocket ←──────────────── transcript line
                                                    ↓
                                             rolling transcript
                                                    ↓
Browser viewer ← WebSocket ←── suggestion ←─── assist/
```

1. **Capture.** The page starts a microphone stream when you click Start.
   Web Audio resamples it to 16 kHz and mixes it to mono. An AudioWorklet
   converts the floating-point samples to signed 16-bit little-endian PCM and
   sends one three-second buffer (96,000 bytes) to the page at a time. The page
   forwards it as a binary frame to `/ws` on the same server.
2. **Transcribe.** `server.py` checks the frame format by message type and size,
   then awaits the chosen transcriber. The dummy emits a numbered demo line.
   The Whisper adapter wraps PCM in a WAV file in memory and uploads each chunk
   independently. Words that straddle a chunk boundary can be missed.
3. **Assist.** The server sends each nonempty transcript line to the browser
   as soon as transcription returns. Each connection owns a window of the
   latest 12 nonblank segments. The prompt builder puts the meeting context
   and instructions in a system message and sends the rolling transcript as a
   separate user message. The chat adapter asks for one short suggestion and
   maps `PASS` to an empty result. The dummy returns a fixed example.
4. **Display.** The page appends transcript lines and replaces the suggestion
   when a new result arrives. It keeps the most recent 100 lines in the DOM.

## WebSocket messages

The browser sends binary PCM frames. The server sends JSON messages with a
`type` of `transcript`, `suggestion`, `error`, or `ready`. The first three
also carry a `text` field. An empty suggestion clears the previous result.
After processing each valid chunk, the server sends `ready`. The browser holds
only the newest waiting chunk while a request is in flight. If processing is
slower than capture, older waiting audio is dropped to keep suggestions timely.

## Adapter boundaries

To add speech recognition, implement `Transcriber.transcribe(pcm)`. To add a
suggestion provider, implement `Assistant.suggest(transcript, meeting_context)`.
Both are async methods so provider calls yield while waiting on the network.
The server lifespan loads settings and manages the provider clients. Audio and
transcript history live in memory for the session. The app is intended to run
on localhost and has no accounts or shared meeting storage.
