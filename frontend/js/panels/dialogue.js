/**
 * Panel 4: Dialogue window - floating chat panel with NPC.
 */
const Dialogue = {
  _idleTimer: null,
  _idleSeconds: 600,
  _currentTab: 'friendly',
  _msgSeq: 0,

  // Floating panel state
  _panelX: null,
  _panelY: null,

  _maximized: false,
  _minimized: false,

  // Action definitions
  _actions: {
    friendly: [
      { name: '微笑', icon: '😊', minRel: null },
      { name: '挥手', icon: '👋', minRel: null },
      { name: '鼓掌', icon: '👏', minRel: null },
      { name: '赞美', icon: '👍', minRel: null },
      { name: '道歉', icon: '🙏', minRel: null },
    ],
    intimate: [
      // acquaintance
      { name: '摸摸头', icon: '🤚', minRel: 'acquaintance' },
      { name: '送礼', icon: '🎁', minRel: 'acquaintance' },
      { name: '搭肩', icon: '🤝', minRel: 'acquaintance' },
      { name: '眨眼', icon: '😉', minRel: 'acquaintance' },
      { name: '勾肩', icon: '🫂', minRel: 'acquaintance' },
      // friend
      { name: '拥抱', icon: '🫂', minRel: 'friend' },
      { name: '牵手', icon: '👫', minRel: 'friend' },
      { name: '捏脸', icon: '🤏', minRel: 'friend' },
      { name: '摸脸', icon: '🖐️', minRel: 'friend' },
      { name: '暖手', icon: '🔥', minRel: 'friend' },
      { name: '头碰头', icon: '🫣', minRel: 'friend' },
      { name: '鼻尖轻碰', icon: '👃', minRel: 'friend' },
      // best_friend - 轻度亲密
      { name: '靠肩', icon: '💆', minRel: 'best_friend' },
      { name: '亲吻', icon: '💋', minRel: 'best_friend' },
      { name: '枕膝', icon: '🦵', minRel: 'best_friend' },
      { name: '深情对视', icon: '👀', minRel: 'best_friend' },
      { name: '双人比心', icon: '🫶', minRel: 'best_friend' },
      { name: '耳旁低语', icon: '🗣️', minRel: 'best_friend' },
      { name: '十指相扣', icon: '🤞', minRel: 'best_friend' },
      { name: '牵手散步', icon: '🚶', minRel: 'best_friend' },
    ],
    couple: [
      // boyfriend - 中度亲密
      { name: '依偎', icon: '💑', minRel: 'boyfriend' },
      { name: '公主抱', icon: '👸', minRel: 'boyfriend' },
      { name: '举高高', icon: '🙌', minRel: 'boyfriend' },
      { name: '背后抱', icon: '🤗', minRel: 'boyfriend' },
      { name: '壁咚', icon: '🧱', minRel: 'boyfriend' },
      { name: '吻手礼', icon: '🫡', minRel: 'boyfriend' },
      { name: '脸颊吻', icon: '😘', minRel: 'boyfriend' },
      { name: '额头吻', icon: '😚', minRel: 'boyfriend' },
      { name: '双人共舞', icon: '💃', minRel: 'boyfriend' },
      { name: '同坐依偎', icon: '🛋️', minRel: 'boyfriend' },
      { name: '枕胸口', icon: '💓', minRel: 'boyfriend' },
      { name: '膝上坐', icon: '💺', minRel: 'boyfriend' },
      // spouse - 高甜/结婚限定
      { name: '浪漫深吻', icon: '❤️', minRel: 'spouse' },
      { name: '求婚', icon: '💍', minRel: 'spouse' },
      { name: '婚礼拥抱', icon: '💒', minRel: 'spouse' },
      { name: '抱怀转圈', icon: '🎠', minRel: 'spouse' },
      { name: '坐腿', icon: '🪑', minRel: 'spouse' },
      { name: '共枕', icon: '🛏️', minRel: 'spouse' },
    ],
    physical: [
      { name: '殴打', icon: '👊', minRel: null, attr: 'strength' },
      { name: '推搡', icon: '🤛', minRel: null, attr: 'strength' },
      { name: '绊倒', icon: '🦵', minRel: null, attr: 'speed' },
      { name: '捉弄', icon: '😜', minRel: null, attr: 'speed' },
    ],
    negative: [
      { name: '生气', icon: '😤', minRel: null },
      { name: '哭泣', icon: '😢', minRel: null },
      { name: '嘲笑', icon: '😏', minRel: null },
    ],
  },

  _relHierarchy: ['stranger', 'acquaintance', 'friend', 'best_friend', 'boyfriend', 'girlfriend', 'spouse', 'parent', 'sibling', 'child'],

  init() {
    const input = document.getElementById('dialogueInput');
    const btn = document.getElementById('btnSend');
    const voiceBtn = document.getElementById('btnVoice');

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.sendMessage();
    });
    btn.addEventListener('click', () => this.sendMessage());
    voiceBtn.addEventListener('click', () => this._toggleVoice());

    Store.on('dialogueMessages', (msgs) => this.renderMessages(msgs));
    Store.on('isNpcTyping', (typing) => this._showTyping(typing));
    Store.on('selectedNpcId', (npcId, oldNpcId) => this._onNpcSelected(npcId, oldNpcId));

    this._initActionPanel();
    this._initDrag();
    this._initMaximize();
    this._initAudioIndicator();
  },

  _initActionPanel() {
    const tabs = document.getElementById('actionsTabs');
    if (tabs) {
      tabs.querySelectorAll('.act-tab').forEach(tab => {
        tab.addEventListener('click', () => {
          this._currentTab = tab.dataset.cat;
          tabs.querySelectorAll('.act-tab').forEach(t => t.classList.remove('active'));
          tab.classList.add('active');
          this._renderActionButtons();
        });
      });
    }
    this._renderActionButtons();
  },

  _renderActionButtons() {
    const grid = document.getElementById('actionsGrid');
    if (!grid) return;

    const actions = this._actions[this._currentTab] || [];
    const npcDetail = Store.get('selectedNpcDetail');
    const relType = npcDetail?.relationship?.relationship_type || 'stranger';

    grid.innerHTML = actions.map(a => {
      const locked = a.minRel && !this._meetsRel(relType, a.minRel);
      const cls = locked ? 'act-btn locked' : 'act-btn';
      const title = locked
        ? `${a.name} — 需要关系: ${this._relCn(a.minRel)}`
        : (a.attr ? `${a.name} — 需要${a.attr === 'strength' ? '力量' : '速度'}判定` : a.name);
      return `<button class="${cls}" data-action="${a.name}" title="${title}"
               ${locked ? 'disabled' : ''}>${a.icon} ${a.name}</button>`;
    }).join('');

    grid.querySelectorAll('.act-btn:not(.locked)').forEach(btn => {
      btn.addEventListener('click', () => {
        this._performAction(btn.dataset.action, btn);
      });
    });
  },

  _meetsRel(current, required) {
    const romanticPairs = new Set(['boyfriend', 'girlfriend']);
    if (romanticPairs.has(current) && romanticPairs.has(required)) return true;
    if (current === 'spouse' && romanticPairs.has(required)) return true;
    const curIdx = this._relHierarchy.indexOf(current);
    const reqIdx = this._relHierarchy.indexOf(required);
    if (curIdx === -1 || reqIdx === -1) return false;
    return curIdx >= reqIdx;
  },

  _performAction(actionName, btn) {
    const npcId = Store.get('selectedNpcId');
    if (!npcId) return;

    Store.addDialogue({
      speakerId: Store.get('playerId'),
      speakerName: '你',
      speakerType: 'player',
      content: actionName,
      _seq: ++this._msgSeq,
    });

    WSClient.send({
      type: 'dialogue_send',
      data: { npc_id: npcId, content: `/${actionName}` },
    });

    Store.set('isNpcTyping', true);
    this._resetIdle();
  },

  enableInput(enable) {
    const input = document.getElementById('dialogueInput');
    const btn = document.getElementById('btnSend');
    const voiceBtn = document.getElementById('btnVoice');
    const actionPanel = document.getElementById('dialogueActions');
    if (input) input.disabled = !enable;
    if (btn) btn.disabled = !enable;
    if (voiceBtn) voiceBtn.disabled = !enable;
    if (actionPanel) actionPanel.style.display = enable ? 'block' : 'none';
  },

  async _onNpcSelected(npcId, oldNpcId) {
    // Skip when GAL overlay is active — GALDialogue handles everything
    const galOverlay = document.getElementById('galDialogueOverlay');
    if (galOverlay && galOverlay.style.display === 'flex') return;

    const header = document.getElementById('dialogueHeader');
    const relDiv = document.getElementById('dialogueRel');

    if (!npcId) {
      if (header) header.innerHTML = '<span class="dialogue-placeholder">选择一个NPC开始对话 💬</span>';
      if (relDiv) relDiv.style.display = 'none';
      this.enableInput(false);
      this._stopIdle();
      Store.clearDialogue();
      return;
    }

    const sameNpc = npcId && oldNpcId && npcId === oldNpcId;

    this.enableInput(true);
    this._resetIdle();
    Store.set('isNpcTyping', false);

    if (!sameNpc) {
      Store.clearDialogue();
      if (window.ttsAudioQueue) {
        window.ttsAudioQueue.clear();
        window.ttsAudioQueue._active = true;
      }
    }

    if (!sameNpc) {
      try {
        const npc = await API.getNpc(npcId);
        const rel = await API.getNpcRelationship(npcId, Store.get('playerId'));
        Store.set('selectedNpcDetail', { ...npc, relationship: rel });
        this._renderActionButtons();

        if (header) {
          header.innerHTML = `
            <span style="font-weight:700;font-size:13px;">💬 与 ${npc.name} 对话</span>
            <div class="dialogue-relationship" id="dialogueRel" style="display:flex;">
              <span class="rel-type">${this._relCn(rel.relationship_type || 'stranger')}</span>
              <div class="rel-bars">
                <div class="rel-bar">
                  <span class="rel-label">❤️</span>
                  <div class="rel-progress"><div class="rel-fill fav-fill" id="favBar" style="width:${((rel.favorability||0)+100)/2}%"></div></div>
                  <span class="rel-value" id="favValue">${rel.favorability || 0}</span>
                </div>
                <div class="rel-bar">
                  <span class="rel-label">👋</span>
                  <div class="rel-progress"><div class="rel-fill fam-fill" id="famBar" style="width:${rel.familiarity || 0}%"></div></div>
                  <span class="rel-value" id="famValue">${rel.familiarity || 0}</span>
                </div>
              </div>
            </div>
            <div class="dialogue-header-actions">
              <button class="btn-header-icon" id="btnDebugRel" title="关系调试" onclick="Dialogue._toggleDebugRel()">⚙️</button>
              <button class="btn-header-icon" id="btnDialogueMax" title="最大化聊天框">⤢</button>
            </div>`;

          // Add debug panel after header
          let debugEl = document.getElementById('debugRelPanel');
          if (!debugEl) {
            debugEl = document.createElement('div');
            debugEl.id = 'debugRelPanel';
            debugEl.className = 'debug-rel-panel';
            debugEl.style.display = 'none';
            debugEl.innerHTML = `
              <div class="debug-rel-row">
                <label>❤️ 好感 <input type="number" id="debugFav" min="-100" max="100" value="${rel.favorability || 0}" style="width:60px"></label>
                <label>👋 熟悉 <input type="number" id="debugFam" min="0" max="100" value="${rel.familiarity || 0}" style="width:60px"></label>
                <label>关系 <select id="debugRelType">
                  ${['stranger','acquaintance','friend','best_friend','boyfriend','girlfriend','spouse','dislike','enemy']
                    .map(t => `<option value="${t}" ${rel.relationship_type===t?'selected':''}>${this._relCn(t)}</option>`).join('')}
                </select></label>
                <button class="btn-save-debug" onclick="Dialogue._applyDebugRel()">应用</button>
              </div>`;
            header.parentNode.insertBefore(debugEl, header.nextSibling);
          } else {
            // Update values in existing debug panel
            const df = document.getElementById('debugFav');
            const dm = document.getElementById('debugFam');
            const dt = document.getElementById('debugRelType');
            if (df) df.value = rel.favorability || 0;
            if (dm) dm.value = rel.familiarity || 0;
            if (dt) dt.value = rel.relationship_type || 'stranger';
          }
        }

        try {
          const history = await API.getDialogueHistory(Store.get('playerId'), npcId, 20);
          if (history && history.length > 0) {
            // Reset seq so history comes before live messages
            this._msgSeq = 0;
            Store.set('dialogueMessages', history.map((d, i) => ({
              speakerId: d.speaker_id,
              speakerName: d.speaker_type === 'npc' ? npc.name : '你',
              speakerType: d.speaker_type,
              content: d.content,
              favorabilityChange: d.favorability_change,
              _seq: ++this._msgSeq,
            })));
          }
        } catch (e) {
          console.error('Failed to load dialogue history:', e);
        }

      } catch (e) {
        console.error('Failed to load NPC for dialogue:', e);
      }
    }
  },

  sendMessage() {
    const input = document.getElementById('dialogueInput');
    const npcId = Store.get('selectedNpcId');
    if (!input || !npcId) return;

    const content = input.value.trim();
    if (!content) return;

    Store.addDialogue({
      speakerId: Store.get('playerId'),
      speakerName: '你',
      speakerType: 'player',
      content: content,
      _seq: ++this._msgSeq,
    });

    WSClient.send({
      type: 'dialogue_send',
      data: { npc_id: npcId, content: content },
    });

    input.value = '';
    Store.set('isNpcTyping', true);
    this._resetIdle();
  },

  // ── Rendering with dialogue/description parsing ────

  renderMessages(msgs) {
    const el = document.getElementById('dialogueMessages');
    if (!el) return;
    this._removeThinkingPlaceholder();
    if (!msgs || msgs.length === 0) {
      el.innerHTML = '<div class="empty-hint">👋 点击场景中的NPC开始对话吧！</div>';
      return;
    }
    const sorted = [...msgs].sort((a, b) => (a._seq || a._ts || 0) - (b._seq || b._ts || 0));
    el.innerHTML = sorted.map((m, mi) => {
      const replayBtn = (m.speakerType === 'npc')
        ? `<div class="msg-replay-row"><button class="btn-replay-msg" data-msg-idx="${mi}" title="重播语音" onclick="Dialogue._replayMsgAudio(this)">🔊 重播</button></div>`
        : '';
      return `
      <div class="msg-bubble ${m.speakerType === 'npc' ? 'npc-msg' : 'player-msg'}" data-msg-idx="${mi}">
        <div class="msg-sender">${m.speakerName}</div>
        <div class="msg-content">${this._renderContent(m, mi)}</div>
        ${this._renderStatusChange(m)}
        ${replayBtn}
      </div>`;
    }).join('');
    el.scrollTop = el.scrollHeight;
    this._updateRelBar(msgs);
  },

  _renderContent(m, msgIdx) {
    let text = this._cleanResponse(m.content);
    if (!text) return '';

    // Parse into segments: dialogue 「」/""  ,  action （） ,  plain text
    const segments = [];
    // Try Chinese guillemets first, then regular quotes
    const re = /(「[^」]*」)|(（[^）]*）)|("[^"]*")|([^「（"]+)/g;
    let match;
    while ((match = re.exec(text)) !== null) {
      if (match[1]) {
        // Dialogue in 「」
        const inner = match[1].slice(1, -1);
        segments.push({ type: 'dialogue', text: inner, raw: match[1] });
      } else if (match[2]) {
        // Action in （）
        segments.push({ type: 'action', text: match[2] });
      } else if (match[3]) {
        // Dialogue in ""
        const inner = match[3].slice(1, -1);
        segments.push({ type: 'dialogue', text: inner, raw: match[3] });
      } else if (match[4] && match[4].trim()) {
        segments.push({ type: 'narrative', text: match[4] });
      }
    }

    if (segments.length === 0) {
      return this._escapeHtml(text);
    }

    return segments.map((seg, si) => {
      const segId = `seg-${msgIdx}-${si}`;
      switch (seg.type) {
        case 'dialogue':
          return `<span class="msg-dialogue" id="${segId}">${this._escapeHtml(seg.text)}</span>`;
        case 'action':
          return `<span class="msg-action">${this._escapeHtml(seg.text)}</span>`;
        default:
          return `<span class="msg-narrative">${this._escapeHtml(seg.text)}</span>`;
      }
    }).join('');
  },

  _collectAudioForMsg(m) {
    // Prefer per-message audio URLs (set during streaming)
    if (m._audioUrls && m._audioUrls.length > 0) {
      console.log('[Replay] using per-message audio URLs:', m._audioUrls.length);
      return [...m._audioUrls];
    }

    // Fallback: search global chunkMap
    const queue = window.ttsAudioQueue;
    if (!queue || !queue._chunkMap || queue._chunkMap.size === 0) {
      console.log('[Replay] chunkMap empty or unavailable');
      return [];
    }
    const text = this._cleanResponse(m.content);
    if (!text) {
      console.log('[Replay] message content empty after cleaning');
      return [];
    }

    const npcId = m.speakerId || Store.get('selectedNpcId') || '';
    const urls = [];
    for (const [sentence, entry] of queue._chunkMap) {
      const url = typeof entry === 'string' ? entry : entry.url;
      const chunkNpcId = typeof entry === 'string' ? '' : (entry.npcId || '');
      if (chunkNpcId && chunkNpcId !== npcId) continue;
      if (this._textContains(text, sentence) && !urls.includes(url)) {
        urls.push(url);
      }
    }
    urls.sort((a, b) => {
      const clean = (s) => s.replace(/[！？。~…，、；;:：\s「」""（）()\n]/g, '');
      const cleanText = clean(text);
      let posA = Infinity, posB = Infinity;
      for (const [s, u] of queue._chunkMap) {
        if (u === a) posA = Math.min(posA, cleanText.indexOf(clean(s)));
        if (u === b) posB = Math.min(posB, cleanText.indexOf(clean(s)));
      }
      return posA - posB;
    });
    console.log('[Replay] collected', urls.length, 'urls from chunkMap for msg:', text.substring(0, 40));
    return urls;
  },

  _textContains(fullText, chunkText) {
    const clean = (s) => s.replace(/[！？。~…，、；;:：\s「」""（）()\n]/g, '');
    const a = clean(fullText);
    const b = clean(chunkText);
    return b.length > 0 && a.includes(b);
  },

  // Pending on-demand TTS requests: request_id → { btn, urls[], msg }
  _pendingReplayRequests: {},

  _replayMsgAudio(btn) {
    // Guard against rapid double-click: button already in progress
    if (btn.classList.contains('loading') || btn.classList.contains('playing')) {
      return;
    }
    const msgIdx = parseInt(btn.dataset.msgIdx);
    const msgs = Store.get('dialogueMessages') || [];
    const sorted = [...msgs].sort((a, b) => (a._seq || a._ts || 0) - (b._seq || b._ts || 0));
    const m = sorted[msgIdx];
    if (!m) { console.log('[Replay] message not found at index', msgIdx); return; }
    console.log('[Replay] attempting replay for msg idx', msgIdx, 'npc:', m.speakerName);

    const urls = this._collectAudioForMsg(m);
    if (urls.length > 0) {
      // Have cached audio → play directly
      this._playReplayUrls(btn, urls);
      return;
    }

    // No cached audio → request TTS generation on demand
    const npcId = m.speakerId || Store.get('selectedNpcId');
    const text = this._cleanResponse(m.content);
    if (!text || !npcId) {
      btn.textContent = '⏳ 无文本';
      setTimeout(() => { btn.textContent = '🔊 重播'; }, 2000);
      return;
    }

    btn.textContent = '⏳ 生成中...';
    btn.classList.add('loading');
    console.log('[Replay] requesting on-demand TTS for:', text.substring(0, 40));

    fetch('/api/v1/tts/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        npc_id: npcId,
        text: text,
        player_id: Store.get('playerId') || 'player_001',
        mood: 'neutral',
      }),
    }).then(r => r.json()).then(resp => {
      if (resp && resp.status === 'ok' && resp.data && resp.data.request_id) {
        const reqId = resp.data.request_id;
        this._pendingReplayRequests[reqId] = {
          btn: btn,
          urls: [],
          msg: m,
        };
        console.log('[Replay] TTS submitted, request_id:', reqId);
        // Timeout after 60s
        setTimeout(() => {
          const pending = this._pendingReplayRequests[reqId];
          if (pending) {
            if (pending.urls.length > 0) {
              this._playReplayUrls(pending.btn, [...pending.urls]);
            } else {
              pending.btn.textContent = '⏳ 语音未就绪';
              pending.btn.classList.remove('loading');
              setTimeout(() => { pending.btn.textContent = '🔊 重播'; }, 2000);
            }
            delete this._pendingReplayRequests[reqId];
          }
        }, 60000);
      } else {
        btn.textContent = '⏳ 请求失败';
        btn.classList.remove('loading');
        setTimeout(() => { btn.textContent = '🔊 重播'; }, 2000);
      }
    }).catch(() => {
      btn.textContent = '⏳ 请求失败';
      btn.classList.remove('loading');
      setTimeout(() => { btn.textContent = '🔊 重播'; }, 2000);
    });
  },

  _playReplayUrls(btn, urls) {
    // Stop any currently playing audio
    if (this._replayAudio) {
      this._replayAudio.pause();
      this._replayAudio = null;
    }
    // Always stop audio queue to guarantee single-channel playback
    if (window.ttsAudioQueue) {
      window.ttsAudioQueue.stop();
    }
    document.querySelectorAll('.btn-replay-msg.playing').forEach(b => b.classList.remove('playing'));

    let idx = 0;
    btn.textContent = '🔊 重播';
    btn.classList.add('playing');
    btn.classList.remove('loading');
    const playNext = () => {
      if (idx >= urls.length) {
        btn.classList.remove('playing');
        this._replayAudio = null;
        console.log('[Replay] playback complete');
        return;
      }
      const url = urls[idx];
      console.log('[Replay] playing chunk', idx, 'url:', url);
      this._replayAudio = new Audio(url);
      this._replayAudio.onended = () => { idx++; playNext(); };
      this._replayAudio.onerror = () => { idx++; playNext(); };
      this._replayAudio.play().catch(() => { idx++; playNext(); });
    };
    playNext();
  },

  _playSegment(btn) {
    const audioUrl = btn.dataset.audio;
    if (!audioUrl) return;
    // Stop any currently playing segment
    if (this._segmentAudio) {
      this._segmentAudio.pause();
      this._segmentAudio = null;
      document.querySelectorAll('.btn-play-segment.playing').forEach(b => b.classList.remove('playing'));
    }
    const audio = new Audio(audioUrl);
    audio.onended = () => {
      btn.classList.remove('playing');
      this._segmentAudio = null;
    };
    audio.onerror = () => {
      btn.classList.remove('playing');
      this._segmentAudio = null;
    };
    audio.play().catch(() => {
      btn.classList.remove('playing');
      this._segmentAudio = null;
    });
    btn.classList.add('playing');
    this._segmentAudio = audio;
  },

  _renderStatusChange(m) {
    if (m.speakerType !== 'npc') return '';
    const parts = [];
    const favNum = parseInt(m.favorabilityChange) || 0;
    if (favNum !== 0) {
      const sign = favNum > 0 ? '+' : '';
      const cls = favNum < 0 ? 'negative' : 'positive';
      parts.push(`<span class="msg-stat ${cls}">❤️ ${sign}${favNum}</span>`);
    }
    if (m.moodBefore && m.moodAfter && m.moodBefore !== m.moodAfter) {
      const moodEmoji = {happy:'😊', neutral:'😐', sad:'😢', angry:'😤', excited:'🤩', bored:'😴', fear:'😨'};
      const before = moodEmoji[m.moodBefore] || m.moodBefore;
      const after = moodEmoji[m.moodAfter] || m.moodAfter;
      parts.push(`<span class="msg-stat mood-change">${before}→${after}</span>`);
    }
    return parts.length ? `<div class="msg-status-row">${parts.join(' ')}</div>` : '';
  },

  _updateRelBar(msgs) {
    const lastNpcMsg = [...msgs].reverse().find(m => m.speakerType === 'npc');
    if (!lastNpcMsg) return;
    const favEl = document.getElementById('favValue');
    const favBar = document.getElementById('favBar');
    if (favEl && lastNpcMsg.favorabilityAfter !== undefined) {
      favEl.textContent = lastNpcMsg.favorabilityAfter;
      if (favBar) favBar.style.width = ((lastNpcMsg.favorabilityAfter + 100) / 2) + '%';
    }
    const famEl = document.getElementById('famValue');
    const famBar = document.getElementById('famBar');
    if (famEl && lastNpcMsg.familiarityAfter !== undefined) {
      famEl.textContent = lastNpcMsg.familiarityAfter;
      if (famBar) famBar.style.width = lastNpcMsg.familiarityAfter + '%';
    }
  },

  _showTyping(typing) {
    const el = document.getElementById('typingIndicator');
    const nameEl = document.getElementById('typingName');
    if (!el) return;
    if (typing) {
      const npc = Store.get('selectedNpcDetail');
      const name = npc?.name || 'NPC';
      if (nameEl) nameEl.textContent = name;
      el.style.display = 'block';
      this._startThinkingFeedback(name);
    } else {
      el.style.display = 'none';
      this._removeThinkingPlaceholder();
    }
  },

  _startThinkingFeedback(npcName) {
    this._removeThinkingPlaceholder();
    // After 5s with no response, show a thinking placeholder bubble
    this._thinkingTimer = setTimeout(() => {
      if (!Store.get('isNpcTyping')) return;
      const msgsEl = document.getElementById('dialogueMessages');
      if (!msgsEl) return;
      const placeholder = document.createElement('div');
      placeholder.className = 'msg-bubble npc-msg thinking-placeholder';
      placeholder.id = 'thinkingPlaceholder';
      placeholder.innerHTML = `
        <div class="msg-sender">${npcName}</div>
        <div class="msg-content thinking-text">让我想想...</div>
      `;
      msgsEl.appendChild(placeholder);
      msgsEl.scrollTop = msgsEl.scrollHeight;
    }, 5000);
  },

  _removeThinkingPlaceholder() {
    if (this._thinkingTimer) {
      clearTimeout(this._thinkingTimer);
      this._thinkingTimer = null;
    }
    const el = document.getElementById('thinkingPlaceholder');
    if (el) el.remove();
  },

  _resetIdle() {
    this._idleSeconds = 600;
    const el = document.getElementById('idleTimer');
    const countEl = document.getElementById('idleCountdown');
    if (el) el.style.display = 'block';

    if (this._idleTimer) clearInterval(this._idleTimer);
    this._idleTimer = setInterval(() => {
      this._idleSeconds--;
      if (countEl) {
        const m = Math.floor(this._idleSeconds / 60);
        const s = this._idleSeconds % 60;
        countEl.textContent = `${m}:${String(s).padStart(2, '0')}`;
      }
      if (this._idleSeconds <= 0) {
        this._stopIdle();
        Store.set('selectedNpcId', null);
        this.enableInput(false);
        App.showMain();
      }
    }, 1000);
  },

  _stopIdle() {
    if (this._idleTimer) {
      clearInterval(this._idleTimer);
      this._idleTimer = null;
    }
    const el = document.getElementById('idleTimer');
    if (el) el.style.display = 'none';
  },

  _cleanResponse(text) {
    // Strip ALL [[...]] tags（consistent with TTS preprocessing）
    return text.replace(/\[\[.*?\]\]/g, '').trim();
  },

  _relCn(type) {
    const map = {
      stranger: '陌生人', acquaintance: '认识的人', friend: '朋友',
      best_friend: '好朋友', boyfriend: '男朋友', girlfriend: '女朋友',
      spouse: '配偶', parent: '父母', sibling: '兄弟姐妹', child: '子女',
      dislike: '讨厌的人', enemy: '仇敌',
    };
    return map[type] || type;
  },

  _escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  },

  _escapeAttr(s) {
    return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  },

  _toggleVoice() {
    const btn = document.getElementById('btnVoice');
    const queue = window.ttsAudioQueue;
    if (!queue) return;
    const enabled = !queue.enabled;
    queue.setEnabled(enabled);
    if (btn) {
      btn.textContent = enabled ? '🔊' : '🔇';
      btn.title = enabled ? '语音播放中 (点击关闭)' : '语音已关闭 (点击开启)';
    }
    this._updateAudioIndicator();
  },

  // ── Floating panel drag ────────────────────────

  _initDrag() {
    const panel = document.getElementById('dialoguePanel');
    const header = document.getElementById('dialogueHeader');
    const handle = document.getElementById('dialogueResizeHandle');
    if (!panel || !header) return;

    // Header drag to move panel
    let dragging = false;
    let startX = 0, startY = 0;
    let panelLeft = 0, panelTop = 0;

    header.addEventListener('mousedown', (e) => {
      // Don't drag when clicking buttons inside header
      if (e.target.tagName === 'BUTTON') return;
      if (this._maximized) return;
      dragging = true;
      const rect = panel.getBoundingClientRect();
      startX = e.clientX;
      startY = e.clientY;
      panelLeft = rect.left;
      panelTop = rect.top;
      panel.classList.add('dragging');
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      let newLeft = panelLeft + dx;
      let newTop = panelTop + dy;

      // Constrain to viewport
      const maxLeft = window.innerWidth - panel.offsetWidth;
      const topbarH = 56;
      newLeft = Math.max(0, Math.min(maxLeft, newLeft));
      newTop = Math.max(topbarH, Math.min(window.innerHeight - 52, newTop));

      panel.style.left = newLeft + 'px';
      panel.style.top = newTop + 'px';
      panel.style.right = 'auto';
      panel.style.bottom = 'auto';
    });

    document.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      panel.classList.remove('dragging');
      document.body.style.userSelect = '';
    });

    // Resize handle (top edge of floating panel)
    if (handle) {
      let resizing = false;
      let resizeStartY = 0;
      let resizeStartH = 0;

      handle.addEventListener('mousedown', (e) => {
        if (this._maximized || this._minimized) return;
        resizing = true;
        resizeStartY = e.clientY;
        resizeStartH = panel.offsetHeight;
        handle.classList.add('dragging');
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'ns-resize';
        e.preventDefault();
        e.stopPropagation(); // don't trigger header drag
      });

      document.addEventListener('mousemove', (e) => {
        if (!resizing) return;
        const dy = resizeStartY - e.clientY;
        const newH = Math.max(120, Math.min(window.innerHeight * 0.85, resizeStartH + dy));
        panel.style.height = newH + 'px';
        panel.style.maxHeight = 'none';
      });

      document.addEventListener('mouseup', () => {
        if (!resizing) return;
        resizing = false;
        handle.classList.remove('dragging');
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
      });
    }
  },

  // ── Maximize / Minimize ─────────────────────────

  _initMaximize() {
    const btn = document.getElementById('btnDialogueMax');
    if (!btn) return;
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      this._cycleDialogueSize();
    });
  },

  _cycleDialogueSize() {
    const panel = document.getElementById('dialoguePanel');
    const btn = document.getElementById('btnDialogueMax');
    if (!panel) return;

    if (this._minimized) {
      panel.classList.remove('minimized');
      this._minimized = false;
      panel.style.height = '';
      panel.style.maxHeight = '';
      if (btn) { btn.textContent = '⤓'; btn.title = '最小化'; }
    } else if (this._maximized) {
      panel.classList.remove('maximized');
      panel.classList.add('minimized');
      this._maximized = false;
      this._minimized = true;
      if (btn) { btn.textContent = '⤡'; btn.title = '展开'; }
    } else {
      panel.classList.add('maximized');
      this._maximized = true;
      if (btn) { btn.textContent = '⤢'; btn.title = '还原'; }
    }
  },

  // ── Audio playback visual indicator ─────────────

  _initAudioIndicator() {
    const queue = window.ttsAudioQueue;
    if (!queue) return;

    queue._onChunkPlayed = (chunk) => {
      this._updateAudioIndicator(chunk);
      // Highlight the corresponding message segment
      this._highlightSegment(chunk);
    };

    queue._onQueueComplete = () => {
      this._updateAudioIndicator(null);
    };
  },

  _updateAudioIndicator(chunk) {
    const indicator = document.getElementById('audioPlayingIndicator');
    if (!indicator) return;

    const queue = window.ttsAudioQueue;
    const isActive = queue && queue.enabled && queue.isPlaying;

    if (isActive) {
      indicator.classList.add('active');
      if (chunk && chunk.text) {
        indicator.textContent = `🔊 ${chunk.text.substring(0, 30)}...`;
      }
    } else {
      indicator.classList.remove('active');
      indicator.textContent = '🔊 语音';
    }
  },

  _highlightSegment(chunk) {
    // Remove previous highlights
    document.querySelectorAll('.msg-chunk-speaking').forEach(el => el.classList.remove('msg-chunk-speaking'));
    if (!chunk || !chunk.text) return;

    // Find matching dialogue segment
    const stripped = chunk.text.replace(/[！？。~…，、\s（）「」""]/g, '');
    document.querySelectorAll('.msg-dialogue').forEach(seg => {
      const segText = (seg.textContent || '').replace(/[！？。~…，、\s🔊]/g, '');
      if (segText.includes(stripped) || stripped.includes(segText)) {
        seg.classList.add('msg-chunk-speaking');
      }
    });
  },

  _toggleDebugRel() {
    const panel = document.getElementById('debugRelPanel');
    if (!panel) return;
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
  },

  async _applyDebugRel() {
    const npcId = Store.get('selectedNpcId');
    const playerId = Store.get('playerId');
    if (!npcId) return;

    const fav = parseInt(document.getElementById('debugFav')?.value) || 0;
    const fam = parseInt(document.getElementById('debugFam')?.value) || 0;
    const relType = document.getElementById('debugRelType')?.value || 'stranger';

    const btn = document.querySelector('.btn-save-debug');
    if (btn) { btn.textContent = '...'; btn.disabled = true; }

    try {
      await API.updateNpcRelationship(npcId, playerId, {
        favorability: fav,
        familiarity: fam,
        relationship_type: relType,
      });
      // Update Store so action buttons see the new relationship
      const detail = Store.get('selectedNpcDetail');
      if (detail?.relationship) {
        detail.relationship.favorability = fav;
        detail.relationship.familiarity = fam;
        detail.relationship.relationship_type = relType;
      }

      // Update local display
      const favEl = document.getElementById('favValue');
      const favBar = document.getElementById('favBar');
      if (favEl) favEl.textContent = fav;
      if (favBar) favBar.style.width = ((fav + 100) / 2) + '%';
      const famEl = document.getElementById('famValue');
      const famBar = document.getElementById('famBar');
      if (famEl) famEl.textContent = fam;
      if (famBar) famBar.style.width = fam + '%';
      const relTypeEl = document.querySelector('#dialogueRel .rel-type');
      if (relTypeEl) relTypeEl.textContent = this._relCn(relType);
      this._renderActionButtons();
      if (btn) btn.textContent = '✓';
    } catch (e) {
      console.error('Failed to update relationship:', e);
      if (btn) btn.textContent = '失败';
    }
    setTimeout(() => { if (btn) { btn.textContent = '应用'; btn.disabled = false; } }, 1500);
  },
};
