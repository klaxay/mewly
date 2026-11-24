const start = document.querySelector("#start");
const stop = document.querySelector("#stop");
const status = document.querySelector("#status");
const transcript = document.querySelector("#transcript");
const suggestion = document.querySelector("#suggestion");

let session;

function finish(message) {
  const current = session;
  session = undefined;
  current?.socket?.close();
  current?.stream?.getTracks().forEach((track) => track.stop());
  if (current?.audio && current.audio.state !== "closed") {
    void current.audio.close();
  }
  start.disabled = false;
  stop.disabled = true;
  status.textContent = message;
}

start.addEventListener("click", async () => {
  start.disabled = true;
  status.textContent = "Starting microphone…";
  const current = {};
  session = current;

  try {
    current.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    current.audio = new AudioContext({ sampleRate: 16000 });
    await current.audio.audioWorklet.addModule("/pcm-worklet.js");
    await current.audio.resume();
    const source = current.audio.createMediaStreamSource(current.stream);
    const worklet = new AudioWorkletNode(current.audio, "pcm-capture", {
      channelCount: 1,
      channelCountMode: "explicit",
    });
    const url = new URL("/ws", location.href);
    url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(url);
    current.socket = socket;
    stop.disabled = false;

    let busy = false;
    let pending;
    function send(buffer) {
      if (socket.readyState !== WebSocket.OPEN) return;
      if (busy) {
        // Retain only the latest waiting chunk when the server falls behind.
        pending = buffer;
        return;
      }
      busy = true;
      socket.send(buffer);
    }

    socket.addEventListener("open", () => {
      if (session !== current) return;
      transcript.replaceChildren();
      suggestion.textContent = "Waiting for audio.";
      status.textContent = "Microphone on.";
      worklet.port.onmessage = ({ data }) => send(data);
      source.connect(worklet).connect(current.audio.destination);
    });
    socket.addEventListener("message", ({ data }) => {
      if (session !== current) return;
      const { type, text } = JSON.parse(data);
      if (type === "transcript") {
        const line = document.createElement("li");
        line.textContent = text;
        transcript.append(line);
        if (transcript.children.length > 100) transcript.firstElementChild.remove();
        transcript.scrollTop = transcript.scrollHeight;
        status.textContent = "Microphone on.";
      } else if (type === "suggestion") {
        suggestion.textContent = text || "No suggestion right now.";
      } else if (type === "error") {
        status.textContent = text;
      } else if (type === "ready") {
        busy = false;
        const next = pending;
        pending = undefined;
        if (next) send(next);
      }
    });
    socket.addEventListener("close", () => {
      if (session === current) finish("Connection closed. Microphone off.");
    });
  } catch (error) {
    finish(`Could not start capture. ${error.message}`);
  }
});

stop.addEventListener("click", () => finish("Microphone off."));
