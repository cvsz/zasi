import { createServer } from 'node:http';

const port = Number(process.env.WORLD_ROOM_PORT || 8090);
const host = process.env.WORLD_ROOM_HOST || '127.0.0.1';
const apiKey = process.env.OPENAI_API_KEY;
const model = process.env.WORLD_ROOM_MODEL || 'gpt-realtime-2';

const instructions = [
  'You are World Room, a playful live worldbuilding companion.',
  'Your job is to co-create settings, characters, conflicts, factions, cultures, mysteries, and scene hooks with the user.',
  'Treat the user as the author. Offer vivid ideas, but never take ownership of their story.',
  'Prefer short, speakable turns. Ask one useful follow-up when the next creative choice is unclear.',
  'Build on details already established in the conversation and call out contradictions gently.',
  'Use sensory language and surprising connections. When useful, propose two or three distinct directions.',
  'Audio is the primary interface: sound natural, expressive, playful, and easy to interrupt.',
].join(' ');

function send(res, status, body, headers = {}) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'access-control-allow-origin': process.env.WORLD_ROOM_CORS_ORIGIN || 'http://127.0.0.1:5174',
    ...headers,
  });
  res.end(payload);
}

async function readJson(req) {
  const chunks = [];
  let total = 0;
  for await (const chunk of req) {
    total += chunk.length;
    if (total > 2_000_000) throw new Error('request too large');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

const server = createServer(async (req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'access-control-allow-origin': process.env.WORLD_ROOM_CORS_ORIGIN || 'http://127.0.0.1:5174',
      'access-control-allow-methods': 'POST, OPTIONS',
      'access-control-allow-headers': 'content-type',
    });
    return res.end();
  }

  if (req.method === 'GET' && req.url === '/health') {
    return send(res, 200, { ok: true, configured: Boolean(apiKey), model });
  }

  if (req.method !== 'POST' || req.url !== '/api/world-room/call') {
    return send(res, 404, { error: 'not_found' });
  }

  if (!apiKey) {
    return send(res, 503, { error: 'OPENAI_API_KEY is not configured on the server.' });
  }

  try {
    const body = await readJson(req);
    if (typeof body.sdp !== 'string' || body.sdp.length < 32) {
      return send(res, 400, { error: 'A valid WebRTC SDP offer is required.' });
    }

    const upstream = await fetch('https://api.openai.com/v1/realtime/calls', {
      method: 'POST',
      headers: {
        authorization: `Bearer ${apiKey}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        sdp: body.sdp,
        session: {
          type: 'realtime',
          model,
          instructions,
          output_modalities: ['audio'],
          audio: {
            input: {
              turn_detection: { type: 'server_vad', create_response: true, interrupt_response: true },
              transcription: { model: 'gpt-live-transcribe' },
            },
            output: { voice: 'marin' },
          },
        },
      }),
    });

    const text = await upstream.text();
    res.writeHead(upstream.status, {
      'content-type': upstream.headers.get('content-type') || 'application/sdp',
      'cache-control': 'no-store',
      'access-control-allow-origin': process.env.WORLD_ROOM_CORS_ORIGIN || 'http://127.0.0.1:5174',
    });
    return res.end(text);
  } catch (error) {
    return send(res, 502, { error: error instanceof Error ? error.message : 'Realtime proxy failed.' });
  }
});

server.listen(port, host, () => {
  console.log(`[World Room] realtime proxy listening on http://${host}:${port}`);
  if (!apiKey) console.warn('[World Room] OPENAI_API_KEY is missing; calls will be rejected.');
});
