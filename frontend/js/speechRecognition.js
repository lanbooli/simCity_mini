/**
 * SpeechRecognition — browser voice input for dialogue.
 * 
 * Uses Web Speech API (webkitSpeechRecognition) for real-time ASR.
 * Supports both single-shot and continuous call-mode.
 * 
 * Call Mode: 
 *   1. Player speaks → silence detected → auto-send
 *   2. Waits for external resume() call (after NPC TTS finishes)
 *   3. Goto 1
 */

class SpeechInput {
  constructor(options = {}) {
    this._onResult = options.onResult || (() => {});
    this._onStatus = options.onStatus || (() => {});
    this._onError = options.onError || (() => {});
    this._onUtteranceComplete = options.onUtteranceComplete || (() => {});
    this._recognition = null;
    this._listening = false;
    this._callMode = false;
    this._finalText = '';
    this._interimText = '';
    this._restartTimer = null;
    this._silenceTimer = null;
    this._silenceTimeout = 1500; // 1.5s silence = utterance end

    // Detect support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    this._supported = !!SpeechRecognition;

    if (this._supported) {
      this._recognition = new SpeechRecognition();
      this._recognition.lang = 'zh-CN';
      this._recognition.continuous = true;
      this._recognition.interimResults = true;
      this._recognition.maxAlternatives = 1;

      this._recognition.onresult = (event) => {
        let interim = '';
        let final = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            final += transcript;
          } else {
            interim += transcript;
          }
        }
        if (final) {
          this._finalText += final;
          this._onResult({ final: this._finalText, interim, isFinal: false });
          // Reset silence timer on new speech
          this._resetSilenceTimer();
        }
        if (interim) {
          this._interimText = interim;
          this._onResult({ final: this._finalText, interim, isFinal: false });
        }
      };

      this._recognition.onerror = (event) => {
        if (event.error === 'no-speech' || event.error === 'aborted') {
          return;
        }
        this._listening = false;
        this._onStatus('error');
        this._onError(new Error(`SpeechRecognition error: ${event.error}`));
        if (event.error === 'network') {
          this._scheduleRestart();
        }
      };

      this._recognition.onend = () => {
        if (this._listening) {
          // In call mode, silence means utterance done — fire complete
          if (this._callMode) {
            this._fireUtteranceComplete();
          } else {
            this._scheduleRestart();
          }
        } else {
          this._onStatus('idle');
        }
      };
    }
  }

  get supported() { return this._supported; }
  get listening() { return this._listening; }
  get currentText() { return this._finalText + this._interimText; }

  // ── Single-shot mode (press to talk, press to send) ──

  start() {
    if (!this._supported) { this._onError(new Error('语音识别不支持')); return; }
    if (this._listening) return;
    this._callMode = false;
    this._listening = true;
    this._finalText = '';
    this._interimText = '';
    this._cancelSilenceTimer();
    try { this._recognition.start(); } catch (_) {}
    this._onStatus('listening');
  }

  stop() {
    this._listening = false;
    this._callMode = false;
    this._cancelRestart();
    this._cancelSilenceTimer();
    if (this._recognition) { try { this._recognition.stop(); } catch (_) {} }
    if (this._finalText.trim()) {
      this._onResult({ final: this._finalText, interim: '', isFinal: true });
    }
    this._onStatus('idle');
  }

  toggle() {
    this.listening ? this.stop() : this.start();
  }

  // ── Call mode (continuous conversation) ──

  startCall() {
    if (!this._supported) { this._onError(new Error('语音识别不支持')); return; }
    this._callMode = true;
    this._finalText = '';
    this._interimText = '';
    this._cancelSilenceTimer();
    this._listen();
    this._onStatus('listening');
  }

  stopCall() {
    this._callMode = false;
    this._listening = false;
    this._cancelRestart();
    this._cancelSilenceTimer();
    if (this._recognition) { try { this._recognition.stop(); } catch (_) {} }
    this._onStatus('idle');
  }

  /** Resume listening after NPC finishes speaking (call mode). */
  resumeListening() {
    if (!this._callMode) return;
    this._finalText = '';
    this._interimText = '';
    this._listen();
    this._onStatus('listening');
  }

  /** Internal: start recognition without resetting call mode. */
  _listen() {
    this._listening = true;
    try { this._recognition.start(); } catch (_) {}
  }

  // ── Silence detection ──

  _resetSilenceTimer() {
    this._cancelSilenceTimer();
    if (!this._callMode) return;
    this._silenceTimer = setTimeout(() => {
      // No new speech for 1.5s → utterance complete
      if (this._listening && this._callMode) {
        this._listening = false;
        try { this._recognition.stop(); } catch (_) {}
        this._fireUtteranceComplete();
      }
    }, this._silenceTimeout);
  }

  _fireUtteranceComplete() {
    this._cancelSilenceTimer();
    this._cancelRestart();
    const text = this._finalText.trim();
    this._finalText = '';
    this._interimText = '';
    if (text) {
      this._onResult({ final: text, interim: '', isFinal: true });
      this._onUtteranceComplete(text);
    } else {
      // No speech detected — resume listening
      this._onStatus('idle');
    }
  }

  _cancelSilenceTimer() {
    if (this._silenceTimer) { clearTimeout(this._silenceTimer); this._silenceTimer = null; }
  }

  _scheduleRestart() {
    this._cancelRestart();
    this._restartTimer = setTimeout(() => {
      if (this._listening) { try { this._recognition.start(); } catch (_) {} }
    }, 300);
  }

  _cancelRestart() {
    if (this._restartTimer) { clearTimeout(this._restartTimer); this._restartTimer = null; }
  }

  clear() { this._finalText = ''; this._interimText = ''; }

  destroy() { this.stopCall(); this._recognition = null; }
}

window.SpeechInput = SpeechInput;
