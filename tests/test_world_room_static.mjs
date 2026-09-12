import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const files = [
  'world-room/index.html',
  'world-room/main.tsx',
  'world-room/styles.css',
  'scripts/world_room_server.mjs',
  'docs/WORLD_ROOM.md',
];

test('World Room surface is complete and local-only by default', async () => {
  const contents = await Promise.all(files.map((file) => readFile(file, 'utf8')));
  for (let i = 0; i < files.length; i += 1) assert.ok(contents[i].length > 100, `${files[i]} is unexpectedly small`);
  const frontend = contents[1];
  const server = contents[3];
  assert.match(frontend, /RTCPeerConnection/);
  assert.match(frontend, /getUserMedia/);
  assert.match(frontend, /createDataChannel/);
  assert.match(server, /OPENAI_API_KEY/);
  assert.match(server, /\/v1\/realtime\/calls/);
  assert.match(server, /gpt-realtime-2/);
  assert.match(server, /loopbackHosts/);
  assert.match(server, /rejects wildcard CORS/);
  assert.match(server, /World Room proxy is local-only/);
});
