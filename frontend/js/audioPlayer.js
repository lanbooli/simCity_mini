/**
 * AudioQueue: gapless TTS audio playback using Web Audio API.
 *
 * Chunks arrive asynchronously from TTS Gateway (one per sentence).
 * Each chunk is decoded and scheduled with precise timing so that
 * consecutive chunks play without gaps or overlaps.
 *
 * Falls back to <audio> elements if Web Audio API is unavailable.
 */
class AudioQueue {
  constructor() {
    this._queue = [];            // pending chunks not yet handed to play loop
    this._playing = false;
    this._enabled = true;
    this._active = true;         // false after stop(); prevents stale chunks from restarting
    this._chunkMap = new Map();  // text → audioUrl for replay
    this._onChunkPlayed = null;
    this._onQueueComplete = null;

    // Web Audio API
    this._audioCtx = null;
    this._scheduledEnd = 0;       // AudioContext time when last buffer finishes
    this._activeSources = [];     // active BufferSourceNodes (for stop())

    // Streaming coordination
    this._nextChunkIndex = 0;
    this._resolveNext = null;     // resolve the play-loop's waiting promise
    this._waitTimer = null;       // timeout for waiting on next chunk
    this._playLoopRunning = false;

    // Feature detection
    this._useWebAudio = !!(window.AudioContext || window.webkitAudioContext);
  }

  get enabled() { return this._enabled; }
  get isPlaying() { return this._playing; }

  setEnabled(val) {
    this._enabled = val;
    if (!val) this.stop();
  }

  // ── Public API ───────────────────────────────────

  enqueue(chunk) {
    if (!this._enabled || !this._active) return;

    // Normalize field names (Python backend uses snake_case)
    const audioUrl = chunk.audioUrl || chunk.audio_url || '';
    const chunkIndex = chunk.chunkIndex ?? chunk.chunk_index ?? 0;
    const text = chunk.text || '';
    const isLast = chunk.isLast ?? chunk.is_last ?? false;

    // Skip duplicate chunks
    if (this._queue.some(c => c.chunkIndex === chunkIndex)) return;

    this._queue.push({ ...chunk, audioUrl, chunkIndex, isLast });
    this._queue.sort((a, b) => a.chunkIndex - b.chunkIndex);

    const npcId = chunk.npcId || chunk.npc_id || '';
    if (text && audioUrl) {
      this._chunkMap.set(text.trim(), { url: audioUrl, npcId });
    }

    // Kick off playback loop on first chunk
    if (!this._playLoopRunning) {
      this._playLoopRunning = true;
      if (this._useWebAudio) {
        this._runWebAudioLoop();
      } else {
        this._runFallbackLoop();
      }
    }

    // Wake up the waiting resolver
    this._tryDeliverNext();
  }

  stop() {
    this._playing = false;
    this._active = false;  // reject stale chunks until reactivated by dialogue_response

    // Unblock the play loop if it's waiting for next chunk
    if (this._resolveNext) {
      clearTimeout(this._waitTimer);
      const r = this._resolveNext;
      this._resolveNext = null;
      r(null);
    }

    // Stop all active Web Audio sources
    this._activeSources.forEach(s => {
      try { s.stop(); } catch (_) {}
    });
    this._activeSources = [];

    // Reset state
    this._queue = [];
    this._nextChunkIndex = 0;
    this._scheduledEnd = 0;
    this._playLoopRunning = false;
  }

  _stopCurrentPlayback() {
    // Stop playback but keep _active=true so incoming chunks are not dropped
    this._playing = false;

    if (this._resolveNext) {
      clearTimeout(this._waitTimer);
      const r = this._resolveNext;
      this._resolveNext = null;
      r(null);
    }

    this._activeSources.forEach(s => {
      try { s.stop(); } catch (_) {}
    });
    this._activeSources = [];

    this._queue = [];
    this._nextChunkIndex = 0;
    this._scheduledEnd = 0;
    this._playLoopRunning = false;
  }

  clear() {
    this.stop();
    this._chunkMap.clear();
  }

  // ── Web Audio API gapless playback ───────────────

  async _getCtx() {
    if (!this._audioCtx) {
      this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (this._audioCtx.state === 'suspended') {
      try { await this._audioCtx.resume(); } catch (_) {}
    }
    return this._audioCtx;
  }

  async _runWebAudioLoop() {
    const ctx = await this._getCtx();
    this._playing = true;
    this._scheduledEnd = ctx.currentTime + 0.05;

    while (this._playing) {
      const chunk = await this._waitForNextChunk();
      if (!chunk) break;  // stopped or timed out

      try {
        const buffer = await this._fetchAndDecode(chunk.audioUrl);
        await this._scheduleBuffer(buffer, chunk);

        if (chunk.isLast) {
          // Wait for last buffer to finish, then stop
          const waitMs = Math.max(0, (this._scheduledEnd - ctx.currentTime) * 1000 + 200);
          await this._sleep(waitMs);
          break;
        }
      } catch (e) {
        console.warn('AudioQueue: chunk decode failed', chunk.chunkIndex, e);
      }
    }

    this._playing = false;
    this._playLoopRunning = false;
    if (this._onQueueComplete) this._onQueueComplete();
  }

  _waitForNextChunk() {
    return new Promise((resolve) => {
      this._resolveNext = resolve;
      this._tryDeliverNext();

      // 30s safety timeout — if no chunk arrives, abort
      this._waitTimer = setTimeout(() => {
        if (this._resolveNext) {
          const r = this._resolveNext;
          this._resolveNext = null;
          r(null);
        }
      }, 30000);
    });
  }

  _tryDeliverNext() {
    if (!this._resolveNext) return;

    const idx = this._queue.findIndex(c => c.chunkIndex === this._nextChunkIndex);
    if (idx >= 0) {
      clearTimeout(this._waitTimer);
      const chunk = this._queue.splice(idx, 1)[0];
      this._nextChunkIndex = chunk.chunkIndex + 1;
      const resolve = this._resolveNext;
      this._resolveNext = null;
      resolve(chunk);
    }
  }

  async _fetchAndDecode(url) {
    const ctx = await this._getCtx();
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const buf = await resp.arrayBuffer();
    return ctx.decodeAudioData(buf);
  }

  async _scheduleBuffer(audioBuffer, chunk) {
    const ctx = await this._getCtx();
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);

    // Schedule precisely at the end of the previous buffer
    const now = ctx.currentTime;
    const startTime = Math.max(now, this._scheduledEnd);

    source.start(startTime);
    this._scheduledEnd = startTime + audioBuffer.duration;
    this._activeSources.push(source);

    source.onended = () => {
      const i = this._activeSources.indexOf(source);
      if (i >= 0) this._activeSources.splice(i, 1);
    };

    // Fire chunk-played callback at the right time
    if (this._onChunkPlayed) {
      const delayMs = Math.max(0, (startTime - now) * 1000);
      setTimeout(() => this._onChunkPlayed(chunk), delayMs + 50);
    }
  }

  // ── Fallback: <audio> element sequential playback ─

  _runFallbackLoop() {
    this._playing = true;
    this._playFallbackNext();
  }

  _playFallbackNext() {
    if (!this._playing) return;

    const chunk = this._queue.shift();
    if (!chunk) {
      this._playing = false;
      this._playLoopRunning = false;
      if (this._onQueueComplete) this._onQueueComplete();
      return;
    }

    this._nextChunkIndex = chunk.chunkIndex + 1;

    const audio = new Audio(chunk.audioUrl);
    audio.onended = () => this._playFallbackNext();
    audio.onerror = () => this._playFallbackNext();
    audio.play().catch(() => this._playFallbackNext());

    if (this._onChunkPlayed) this._onChunkPlayed(chunk);
  }

  _sleep(ms) {
    return new Promise(r => setTimeout(r, Math.max(0, ms)));
  }
}

// Singleton for dialogue panel
window.ttsAudioQueue = new AudioQueue();
window.ttsAudioQueue._version = 2;  // bump to verify new code is loaded
