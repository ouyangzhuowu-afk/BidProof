import assert from 'node:assert/strict';
import test from 'node:test';
import { openSessionChannel } from '../src/core/session-channel.js';

function browserPair() {
  const peers = new Set(); const sent = [];
  class Channel {
    constructor(name) { this.name = name; this.onmessage = null; peers.add(this); }
    postMessage(data) {
      sent.push(data);
      for (const peer of peers) if (peer !== this && peer.name === this.name) peer.onmessage?.({ data });
    }
    close() { peers.delete(this); }
  }
  const host = () => {
    const target = new EventTarget(); const listeners = new Set();
    return { BroadcastChannel: Channel, listeners,
      addEventListener(type, callback) { listeners.add(callback); target.addEventListener(type, callback); },
      removeEventListener(type, callback) { listeners.delete(callback); target.removeEventListener(type, callback); },
      emit(type, persisted = false) { const event = new Event(type); Object.defineProperty(event, 'persisted', { value: persisted }); target.dispatchEvent(event); },
    };
  };
  return { one: host(), two: host(), peers, sent };
}

await test('two tabs exchange only a fixed invalidation signal without echo or private data', () => {
  const browser = browserPair(); let a = 0; let b = 0;
  const first = openSessionChannel(() => { a++; }, browser.one);
  const second = openSessionChannel(() => { b++; }, browser.two);
  try {
    first.publish(); assert.equal(a, 0); assert.equal(b, 1);
    second.publish(); assert.equal(a, 1); assert.equal(b, 1);
    assert.deepEqual(browser.sent, ['session-changed', 'session-changed']);
    for (const peer of browser.peers) peer.onmessage({ data: { event: 'session-changed', token: 'invalid' } });
    assert.equal(a, 1); assert.equal(b, 1);
  } finally { first.close(); second.close(); }
  assert.equal(browser.peers.size, 0);
  assert.equal(browser.one.listeners.size + browser.two.listeners.size, 0);
});

await test('page lifecycle closes channels, ignores queued old events and revalidates on bfcache restore', () => {
  const browser = browserPair(); let changed = 0;
  const handle = openSessionChannel(() => { changed++; }, browser.one);
  const old = [...browser.peers][0]; const queued = old.onmessage;
  browser.one.emit('pagehide'); assert.equal(browser.peers.size, 0); assert.equal(old.onmessage, null);
  queued({ data: 'session-changed' }); assert.equal(changed, 0);
  browser.one.emit('pageshow', true); assert.equal(changed, 1); assert.equal(browser.peers.size, 1);
  queued({ data: 'session-changed' }); assert.equal(changed, 1);
  handle.close(); handle.close(); browser.one.emit('pageshow', true);
  assert.equal(browser.peers.size, 0); assert.equal(changed, 1); assert.equal(browser.one.listeners.size, 0);
});

await test('unsupported or blocked BroadcastChannel leaves the local auth flow usable', () => {
  for (const channel of [undefined, class { constructor() { throw new Error('blocked'); } }]) {
    const browser = browserPair(); browser.one.BroadcastChannel = channel;
    const handle = openSessionChannel(() => { throw new Error('unexpected message'); }, browser.one);
    assert.doesNotThrow(() => handle.publish()); handle.close(); assert.equal(browser.one.listeners.size, 0);
  }
});
