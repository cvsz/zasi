# World Room

World Room is an audio-first worldbuilding companion built as a bounded ZASI creative surface. It uses the OpenAI Realtime API over WebRTC for speech-to-speech interaction instead of a request/response text loop.

## Architecture

```text
Browser
  ├─ getUserMedia()
  ├─ RTCPeerConnection + microphone track
  ├─ remote audio playback
  └─ Realtime data channel for transcripts/events
          │
          │ SDP offer
          ▼
Local World Room proxy (scripts/world_room_server.mjs)
  ├─ owns OPENAI_API_KEY
  ├─ supplies Realtime session instructions/model
  └─ POST /v1/realtime/calls to OpenAI
          │
          ▼
OpenAI Realtime WebRTC session
```

The browser never receives `OPENAI_API_KEY`. The local proxy owns the API credential and the Realtime session configuration. This keeps the credential out of client JavaScript and follows the current WebRTC Realtime call pattern.

## Model

The default is `gpt-realtime-2.1`, the current reasoning-capable Realtime model used by this implementation. Override with `WORLD_ROOM_MODEL` when testing another supported Realtime model.

## Local setup

1. Export the OpenAI API key in the shell that starts the proxy:

```bash
export OPENAI_API_KEY="..."
```

PowerShell:

```powershell
$env:OPENAI_API_KEY="..."
```

2. Install the existing project dependencies:

```bash
npm ci
```

3. Start the Realtime proxy:

```bash
npm run world-room:server
```

4. In another terminal start the UI:

```bash
npm run world-room:dev
```

5. Open `http://127.0.0.1:5174/` and allow microphone access.

The proxy listens on `127.0.0.1:8090` by default. `WORLD_ROOM_HOST`, `WORLD_ROOM_PORT`, `WORLD_ROOM_MODEL`, and `WORLD_ROOM_CORS_ORIGIN` can override local defaults.

## Session lifecycle

- The browser requests microphone access only when the user enters the room.
- A WebRTC offer is created in the browser and sent to the local proxy.
- The proxy creates the Realtime call with `POST /v1/realtime/calls` and returns the SDP answer.
- Audio flows directly between the browser peer connection and the Realtime service after negotiation; the proxy is not an audio relay.
- The data channel carries Realtime events used for transcript display and error state.
- Leaving the room closes the data channel, peer connection, and local microphone tracks.
- Connection failures move the UI into `RECOVER`; the user can start a fresh session without reloading the page.

## Latency notes

WebRTC is used because the experience depends on low-latency audio and natural interruption. Keep prompts concise, avoid unnecessary client round trips, and let server VAD manage turn boundaries. `gpt-realtime-2.1` improves interruption behavior and silence/noise handling over GPT-Realtime-2; keep the default interaction lightweight and use `WORLD_ROOM_MODEL` when testing a deliberate quality/latency/cost tradeoff.

## Permissions and recovery

Microphone permission is browser-controlled and must be granted by the user. The app does not attempt to persist microphone access or capture audio before the user starts a session. A denied permission, unavailable device, failed SDP exchange, or Realtime error is surfaced as a recoverable UI error.

The current proxy is intentionally a local-development server. Do not expose it publicly without adding authenticated access, rate limiting, origin controls appropriate to the deployment, and an application-level session/token policy.

## Validation checklist

- [ ] Browser asks for microphone permission only after clicking **Enter the room**.
- [ ] Denying microphone permission produces a readable recoverable error.
- [ ] `GET /health` reports `configured: true` when `OPENAI_API_KEY` is set.
- [ ] A successful connection changes READY → CONNECTING → LIVE.
- [ ] User speech reaches the Realtime session without a text request/response loop.
- [ ] Assistant audio is audible through the remote WebRTC track.
- [ ] User and assistant transcript events appear in Room Memory when available.
- [ ] Mute disables the local microphone track without destroying the session.
- [ ] Ending the room stops local microphone tracks and closes the peer connection.
- [ ] Disconnecting the network produces a recoverable state and a fresh session can be started.
- [ ] Invalid/missing `OPENAI_API_KEY` is rejected by the proxy without exposing credentials to the browser.
- [ ] `npm run world-room:build` completes successfully before packaging a UI artifact.
- [ ] The proxy is not deployed publicly without authentication and rate limiting.

## OpenAI references

Use the current Realtime API documentation when changing this integration. The implementation deliberately uses the Realtime WebRTC Calls surface rather than the deprecated request/response audio pattern.
