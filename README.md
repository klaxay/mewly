# mewly

A small, open live meeting copilot built for learning. Start the microphone and
watch transcript lines and short suggestions appear in the same browser tab.

## Run locally

You need Python 3.11 or newer and a browser with microphone and AudioWorklet
support. From the repository root, run:

```sh
make install
make run-offline
```

Open [mewly on localhost](http://127.0.0.1:8000), select **Start microphone**,
and grant microphone access. The first demo line and suggestion arrive after
about three seconds. The dummy adapters return sample text even in silence and
require no keys or network calls after installation. **Stop** releases the
microphone. Starting again opens a fresh session.

Without Make, run `python3 -m venv .venv`,
`.venv/bin/python -m pip install -r requirements.txt`, then
`MEWLY_TRANSCRIBER=dummy MEWLY_ASSISTANT=dummy .venv/bin/python -m uvicorn server:app --ws-max-size 96000 --ws-max-queue 1`.

## Try real transcription or suggestions

Copy `.env.example` to `.env` and set the desired switches:

- `MEWLY_TRANSCRIBER=whisper` batches microphone chunks and sends them to
  OpenAI's audio transcriptions endpoint. Set `OPENAI_API_KEY`.
  `WHISPER_MODEL` defaults to `gpt-4o-transcribe`. `WHISPER_WINDOW_SECONDS`
  defaults to 6 and rounds up to a whole three-second capture chunk.
- `MEWLY_ASSISTANT=openai` sends recent transcript and optional `MEETING_CONTEXT`
  (for example, an agenda or your role) to OpenAI Chat Completions. It uses
  `OPENAI_API_KEY` and defaults to `gpt-4o-mini`. For a compatible provider,
  set `ASSISTANT_BASE_URL` to its API base (typically ending in `/v1`),
  `ASSISTANT_API_KEY` to its key, and `ASSISTANT_MODEL` to its model.

Run `make run` to use those settings. Both switches default to `dummy` and
can be set independently. Shell variables take precedence over `.env`.
Use real providers only for meetings where participants have agreed to audio
capture and external processing. The viewer captures the selected microphone.
For remote voices, the microphone must be able to hear them.

## Tests

Run `make test` or `.venv/bin/python -m pytest -q`. The suite covers the rolling
transcript, prompt assembly, and provider requests and responses using mocked HTTP.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the audio format, socket messages, and
adapter boundaries.
