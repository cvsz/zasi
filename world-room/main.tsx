import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Status = 'idle' | 'connecting' | 'live' | 'error';
type Message = { role: 'user' | 'world'; text: string };

const PROXY_URL = import.meta.env.VITE_WORLD_ROOM_PROXY || 'http://127.0.0.1:8090';

function WorldRoom() {
  const [status, setStatus] = useState<Status>('idle');
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [muted, setMuted] = useState(false);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const transcriptRef = useRef<Record<string, string>>({});

  const append = (role: Message['role'], text: string) => {
    if (!text.trim()) return;
    setMessages((current) => [...current, { role, text: text.trim() }]);
  };

  const handleEvent = (raw: string) => {
    try {
      const event = JSON.parse(raw) as { type?: string; delta?: string; transcript?: string; item_id?: string };
      if (event.type === 'conversation.item.input_audio_transcription.completed' && event.transcript) {
        append('user', event.transcript);
      }
      if (event.type === 'response.output_audio_transcript.delta' && event.delta) {
        const key = event.item_id || 'current';
        transcriptRef.current[key] = (transcriptRef.current[key] || '') + event.delta;
      }
      if (event.type === 'response.output_audio_transcript.done') {
        const key = event.item_id || 'current';
        const text = transcriptRef.current[key];
        if (text) append('world', text);
        delete transcriptRef.current[key];
      }
      if (event.type === 'error') setError('Realtime session reported an error. Try reconnecting.');
    } catch {
      // Ignore non-JSON data-channel frames.
    }
  };

  const disconnect = () => {
    dcRef.current?.close();
    pcRef.current?.close();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    dcRef.current = null;
    pcRef.current = null;
    streamRef.current = null;
    if (audioRef.current) audioRef.current.srcObject = null;
    setStatus('idle');
  };

  const connect = async () => {
    if (status === 'live' || status === 'connecting') return;
    setStatus('connecting');
    setError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const pc = new RTCPeerConnection();
      pcRef.current = pc;
      pc.ontrack = (event) => {
        const [trackStream] = event.streams;
        if (audioRef.current && trackStream) {
          audioRef.current.srcObject = trackStream;
          void audioRef.current.play().catch(() => undefined);
        }
      };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === 'connected') setStatus('live');
        if (['failed', 'disconnected', 'closed'].includes(pc.connectionState)) setStatus('error');
      };
      const dc = pc.createDataChannel('oai-events');
      dcRef.current = dc;
      dc.onmessage = (event) => handleEvent(String(event.data));
      stream.getTracks().forEach((track) => pc.addTrack(track, stream));

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const answer = await fetch(`${PROXY_URL}/api/world-room/call`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ sdp: offer.sdp }),
      });
      const answerText = await answer.text();
      if (!answer.ok) throw new Error(answerText || `Realtime proxy returned ${answer.status}`);
      await pc.setRemoteDescription({ type: 'answer', sdp: answerText });
    } catch (cause) {
      disconnect();
      setStatus('error');
      setError(cause instanceof Error ? cause.message : 'Could not start the microphone session.');
    }
  };

  const sendText = () => {
    const text = draft.trim();
    const dc = dcRef.current;
    if (!text || !dc || dc.readyState !== 'open') return;
    append('user', text);
    dc.send(JSON.stringify({
      type: 'conversation.item.create',
      item: { type: 'message', role: 'user', content: [{ type: 'input_text', text }] },
    }));
    dc.send(JSON.stringify({ type: 'response.create' }));
    setDraft('');
  };

  useEffect(() => () => disconnect(), []);

  return (
    <main className="room">
      <audio ref={audioRef} autoPlay />
      <header className="topbar">
        <div className="brand"><span className="sigil">✦</span><div><strong>WORLD ROOM</strong><small>J.A.R.V.I.S. creative chamber</small></div></div>
        <div className={`status status-${status}`}><span />{status === 'live' ? 'LIVE' : status === 'connecting' ? 'CONNECTING' : status === 'error' ? 'RECOVER' : 'READY'}</div>
      </header>

      <section className="hero">
        <div className="orb" aria-hidden="true"><div className="orb-core" /><div className="ring ring-a" /><div className="ring ring-b" /></div>
        <p className="eyebrow">AUDIO-FIRST WORLDBUILDING</p>
        <h1>Open a door.<br /><em>Make a world.</em></h1>
        <p className="lede">Speak an idea. World Room turns it into places, people, pressure, and the next scene.</p>

        <button className={`mic ${status === 'live' ? 'mic-live' : ''}`} onClick={status === 'live' ? disconnect : connect} aria-label={status === 'live' ? 'End session' : 'Start voice session'}>
          <span className="mic-icon">{status === 'live' ? '■' : '●'}</span>
          <span>{status === 'live' ? 'Leave the room' : status === 'connecting' ? 'Opening the room…' : 'Enter the room'}</span>
        </button>
        <div className="controls"><button onClick={() => setMuted((value) => !value)} disabled={!streamRef.current}>{muted ? 'Unmute mic' : 'Mute mic'}</button><button onClick={disconnect}>Reset</button></div>
        {error && <div className="error">{error}</div>}
      </section>

      <section className="conversation">
        <div className="conversation-head"><span>ROOM MEMORY</span><span>{messages.length ? `${messages.length} turns` : 'Nothing written yet'}</span></div>
        <div className="messages">
          {messages.length === 0 && <div className="empty"><span>“</span><p>Try: “Give me a city built inside the ribs of a sleeping leviathan.”</p></div>}
          {messages.map((message, index) => <article className={`message ${message.role}`} key={`${index}-${message.text}`}><span className="message-role">{message.role === 'user' ? 'YOU' : 'WORLD ROOM'}</span><p>{message.text}</p></article>)}
        </div>
        <form className="text-fallback" onSubmit={(event) => { event.preventDefault(); sendText(); }}>
          <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Type a spark if you prefer…" disabled={status !== 'live'} />
          <button disabled={status !== 'live' || !draft.trim()}>Send</button>
        </form>
      </section>

      <footer><span>WebRTC · speech-to-speech · server-side API key</span><span>World Room is creative play, not an autonomous operator.</span></footer>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<WorldRoom />);
