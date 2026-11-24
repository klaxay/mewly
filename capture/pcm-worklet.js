// The 16 kHz AudioContext resamples the microphone before it reaches this node.
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.allocateChunk();
  }

  allocateChunk() {
    this.chunk = new DataView(new ArrayBuffer(sampleRate * 3 * 2));
    this.offset = 0;
  }

  process([input]) {
    // The node mixes its input to mono. With no input there is nothing to send.
    for (const sample of input[0] ?? []) {
      const clamped = Math.max(-1, Math.min(1, sample));
      const pcm = Math.round(clamped * (clamped < 0 ? 32768 : 32767));
      this.chunk.setInt16(this.offset, pcm, true);
      this.offset += 2;

      if (this.offset === this.chunk.byteLength) {
        const buffer = this.chunk.buffer;
        // Transfer ownership of the finished buffer to the page without copying.
        this.port.postMessage(buffer, [buffer]);
        this.allocateChunk();
      }
    }
    // Leave the output silent so the microphone is never played back.
    return true;
  }
}

registerProcessor("pcm-capture", PcmCapture);
