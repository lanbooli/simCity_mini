/**
 * GAL Dialogue — full-screen visual novel style dialogue panel.
 * Reuses Dialogue core logic (actions, relationship checks, text parsing, audio, idle).
 */
const GALDialogue = {
  _mode: 'simple',       // 'simple' | 'expanded'
  _currentTab: 'friendly',
  _msgSeq: 0,
  _idleTimer: null,
  _idleSeconds: 600,
  _moodEmoji: { happy: '😊', excited: '🤩', neutral: '😐', sad: '😢', angry: '😠', bored: '🥱' },
  _pendingReplayRequests: {},
  _replayAudio: null,
  _allMsgs: [],          // Full message history

  init() {
    document.getElementById('galBtnBack').addEventListener('click', () => this.hide());
    document.getElementById('galBtnSend').addEventListener('click', () => this.sendMessage());
    document.getElementById('galBtnVoice').addEventListener('click', () => this._toggleVoice());
    document.getElementById('galBtnDebug').addEventListener('click', () => this._toggleDebug());
    document.getElementById('galBtnHistory').addEventListener('click', () => this._showHistory());
    document.getElementById('galBtnCloseHistory').addEventListener('click', () => this._hideHistory());
    document.getElementById('galBtnApplyDebug').addEventListener('click', () => this._applyDebug());
    document.getElementById('galBtnCollapse').addEventListener('click', () => this._setMode('simple'));
    document.getElementById('galDialogueInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.sendMessage();
    });
    this._initSpeechInput();
    this._initCallMode();

    // Date button
    const galDateBtn = document.getElementById('galBtnDate');
    if (galDateBtn) {
      galDateBtn.addEventListener('click', () => {
        if (Dialogue._dateState && Dialogue._dateState.inDate) {
          alert('你已经在约会中了');
          return;
        }
        Dialogue._showDateConfig();
      });
    }
    // Date leave button in GAL bar
    const galDateLeave = document.getElementById('galDateLeave');
    if (galDateLeave) {
      galDateLeave.addEventListener('click', () => Dialogue._handleDateLeave());
    }

    // Expanded action tabs
    document.getElementById('galActionsTabs').querySelectorAll('.gal-act-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        this._currentTab = tab.dataset.cat;
        document.getElementById('galActionsTabs').querySelectorAll('.gal-act-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        this._renderExpandedActions();
      });
    });

    // Listen for dialogue responses
    Store.on('dialogueMessages', (msgs) => this._onMessagesUpdated(msgs));
    Store.on('isNpcTyping', (typing) => this._showTyping(typing));

    // Listen for NPC state changes to update portrait status
    Store.on('npcs', () => {
      const overlay = document.getElementById('galDialogueOverlay');
      if (!overlay || overlay.style.display === 'none') return;
      const npcId = Store.get('selectedNpcId');
      const npc = Store.get('selectedNpcDetail');
      if (npcId && npc) {
        this._renderPortrait(npc);
        var dmsgs = Store.get('dialogueMessages') || [];
        this._renderTextbox(dmsgs);
        this._updateSceneDisplay(npc);
      }
    });
    // Also update when player data changes
    Store.on('playerData', (pd) => {
      if (pd && Store.get('selectedNpcId')) {
        const npc = Store.get('selectedNpcDetail');
        if (npc) this._renderPortrait(npc);
      }
    });
  },

  // ── Show / Hide ──────────────────────────────

  async show(npcId) {
    if (!npcId) return;
    const overlay = document.getElementById('galDialogueOverlay');
    if (!overlay) return;

    // Hide old floating dialogue panel
    const floatPanel = document.getElementById('dialoguePanel');
    if (floatPanel) floatPanel.style.display = 'none';

    // Reset state
    this._mode = 'simple';
    this._msgSeq = 0;
    // Ensure debug panel starts hidden
    const debugPanel = document.getElementById('galDebugPanel');
    if (debugPanel) debugPanel.style.display = 'none';
    this._allMsgs = [];
    this._storeMsgsProcessed = 0;
    Store.clearDialogue();
    if (window.ttsAudioQueue) {
      window.ttsAudioQueue.clear();
      window.ttsAudioQueue._active = true;
      // Clear stale chunkMap to prevent voice mixing between NPCs
      if (window.ttsAudioQueue._chunkMap) window.ttsAudioQueue._chunkMap.clear();
    }

    // Load NPC data
    try {
      const npc = await API.getNpc(npcId);
      const rel = await API.getNpcRelationship(npcId, Store.get('playerId'));
      Store.set('selectedNpcDetail', { ...npc, relationship: rel });

      // Render
      this._renderPortrait(npc);
      this._updateSceneDisplay(npc);
      this._updateRelDisplay(rel);
      this._setMode('simple');
      this._renderSimpleActions();
      this._renderTextbox(null);

      // Topbar title
      document.getElementById('galTitle').textContent = `💬 与 ${npc.name} 对话`;

      // Enable input
      document.getElementById('galDialogueInput').disabled = false;
      document.getElementById('galBtnSend').disabled = false;
      const galMicBtn = document.getElementById('galBtnMic');
      if (galMicBtn) galMicBtn.disabled = false;
      const galCallBtn = document.getElementById('galBtnCall');
      if (galCallBtn) galCallBtn.disabled = false;
      document.getElementById('galDialogueInput').focus();

      // Load history
      try {
        const history = await API.getDialogueHistory(Store.get('playerId'), npcId, 20);
        if (history && history.length > 0) {
          this._allMsgs = history.map((d) => ({
            speakerId: d.speaker_id,
            speakerName: d.speaker_type === 'npc' ? npc.name : '你',
            speakerType: d.speaker_type,
            content: d.content,
            favorabilityChange: d.favorability_change,
            _seq: ++this._msgSeq,
          }));
          this._renderTextbox(this._allMsgs);
    this._resetIdle();
        }
      } catch (e) {
        console.error('Failed to load dialogue history:', e);
      }

      // Load any Store messages that arrived before panel opened
      // (NPC-initiated greetings from websocket.js now call Store.addDialogue directly)
      var storeMsgs = Store.get('dialogueMessages') || [];
      var existingSeqs = new Set(this._allMsgs.map(m => m._seq));
      for (var si = 0; si < storeMsgs.length; si++) {
        var sm = storeMsgs[si];
        if (sm._isAmbient) continue;
        if (!existingSeqs.has(sm._seq)) {
          this._allMsgs.push({ ...sm });
          existingSeqs.add(sm._seq);
        }
      }
      this._storeMsgsProcessed = storeMsgs.length;
      if (this._allMsgs.length > 0) {
        this._renderTextbox(this._allMsgs);
      }

      // Show overlay
      overlay.style.display = 'flex';
      overlay.classList.remove('hiding');

      // Debug panel — set initial values
      document.getElementById('galDebugFav').value = rel.favorability || 0;
      document.getElementById('galDebugFam').value = rel.familiarity || 0;
      document.getElementById('galDebugRelType').value = rel.relationship_type || 'stranger';

      this._resetIdle();
    } catch (e) {
      console.error('Failed to load NPC for GAL dialogue:', e);
    }
  },

  hide() {
    const overlay = document.getElementById('galDialogueOverlay');
    if (!overlay) return;
    overlay.classList.add('hiding');
    setTimeout(() => {
      overlay.style.display = 'none';
      overlay.classList.remove('hiding');
      // Restore floating panel visibility
      const floatPanel = document.getElementById('dialoguePanel');
      if (floatPanel) floatPanel.style.display = '';
    }, 250);

    this._stopIdle();
    Store.set('selectedNpcId', null);
    // Reset debug panel to hidden
    const debugPanel = document.getElementById('galDebugPanel');
    if (debugPanel) debugPanel.style.display = 'none';
    // Return to main view
    if (App.showMain) App.showMain();

    // Clear TTS
    if (window.ttsAudioQueue) {
      window.ttsAudioQueue.clear();
      window.ttsAudioQueue._active = true;
    }
  },

  // ── Character Portrait Rendering (left-center-right) ──

  _setCharImage(side, imgUrl) {
    const emojiEl = document.getElementById(`galChar${side}Emoji`);
    const imgEl = document.getElementById(`galChar${side}Img`);
    if (!emojiEl || !imgEl) return;
    if (imgUrl) {
      imgEl.src = imgUrl;
      imgEl.style.display = 'block';
      emojiEl.style.display = 'none';
      imgEl.onerror = () => {
        imgEl.style.display = 'none';
        emojiEl.style.display = 'block';
      };
    } else {
      imgEl.style.display = 'none';
      emojiEl.style.display = 'block';
    }
  },

  _renderPortrait(npc) {
    const state = Store.get('npcs')?.[npc.id] || {};
    const mood = state.mood || npc.current_mood || 'neutral';
    const moodEmoji = { happy: '😊', excited: '🤩', neutral: '😐', sad: '😢', angry: '😠', bored: '🥱' };

    // NPC left side: fullbody > avatar > emoji
    const fullbody = npc.appearance?.fullbody || npc.fullbody || '';
    const avatar = npc.appearance?.avatar || npc.avatar || '';
    const npcImg = fullbody || avatar;
    const genderEmoji = npc.gender === 'female' ? '👩' : npc.gender === 'male' ? '👨' : '🧑';
    document.getElementById('galCharLeftEmoji').textContent = genderEmoji;
    document.getElementById('galCharLeftName').textContent = npc.name;
    this._setCharImage('Left', npcImg);

    // Player right side: fullbody > avatar > emoji
    const playerData = Store.get('playerData');
    if (playerData) {
      const playerAppearance = (typeof playerData.appearance === 'string')
        ? JSON.parse(playerData.appearance) : (playerData.appearance || {});
      const playerFullbody = playerAppearance.fullbody || '';
      const playerAvatar = playerAppearance.avatar || '';
      const playerImg = playerFullbody || playerAvatar;
      document.getElementById('galCharRightEmoji').textContent = '🧑';
      document.getElementById('galCharRightName').textContent = playerData.name || '我';
      this._setCharImage('Right', playerImg);
    }

    // NPC status below portrait
    const isSleeping = state.is_sleeping || false;
    const activity = (isSleeping ? '😴 ' : '') + (state.current_activity || npc.current_activity || '闲逛中');
    const aa = state.auto_action;
    const autoText = aa ? ` · ${aa.icon || ''} ${aa.display_text || aa.action_name}` : '';
    const moodIcon = moodEmoji[mood] || '😐';
    document.getElementById('galCharLeftStatus').textContent = `${activity}${autoText}`;
    document.getElementById('galCharLeftMood').textContent = moodIcon;

    // NPC physiology stats
    var phys = state.physiology;
    var physEl = document.getElementById('galCharLeftPhysiology');
    if (physEl) {
      if (phys) {
        var icons = { hunger: '🍽️', thirst: '💧', energy: '⚡', social: '👥' };
        var colors = { hunger: '#FF8A80', thirst: '#81D4FA', energy: '#FFD54F', social: '#A5D6A7' };
        var html = '';
        // HP bar (always visible, red when low)
        var hp = Math.max(0, Math.min(100, phys.hp || 100));
        var hpColor = hp < 30 ? '#FF5252' : (hp < 60 ? '#FFAB40' : '#69F0AE');
        html += '<div class="gal-phys-row">'
          + '<span class="gal-phys-icon">❤️</span>'
          + '<div class="gal-phys-bar-bg"><div class="gal-phys-bar-fill" style="width:' + hp + '%;background:' + hpColor + '"></div></div>'
          + '<span class="gal-phys-label">' + Math.round(hp) + '</span>'
          + '</div>';
        for (var key of ['hunger', 'thirst', 'energy', 'social']) {
          var val = Math.max(0, Math.min(100, phys[key] || 0));
          html += '<div class="gal-phys-row">'
            + '<span class="gal-phys-icon">' + icons[key] + '</span>'
            + '<div class="gal-phys-bar-bg"><div class="gal-phys-bar-fill" style="width:' + val + '%;background:' + colors[key] + '"></div></div>'
            + '<span class="gal-phys-label">' + Math.round(val) + '</span>'
            + '</div>';
        }
        physEl.innerHTML = html;
        physEl.style.display = '';
      } else {
        physEl.style.display = 'none';
      }
    }

    // Player mood/status (if available)
    document.getElementById('galCharRightStatus').textContent = '';
    document.getElementById('galCharRightMood').textContent = '';

    // Update top-bar mood indicator
    const moodStat = document.getElementById('galMoodStat');
    if (moodStat) moodStat.textContent = `${moodEmoji[mood] || '😐'} ${mood}`;
  },

  // ── Textbox Rendering ────────────────────────

  _renderTextbox(msgs) {
    const historyEl = document.getElementById('galTextboxHistory');
    const speakerEl = document.getElementById('galTextboxSpeaker');
    const msgEl = document.getElementById('galTextboxMsg');

    if (!msgs || msgs.length === 0) {
      historyEl.innerHTML = '';
      speakerEl.textContent = 'NPC';
      msgEl.innerHTML = '';
      return;
    }

    const sorted = [...msgs].filter(m => !m._isAmbient).sort((a, b) => (a._seq || a._ts || 0) - (b._seq || b._ts || 0));

    // Last message is current; previous 1-2 are history
    const current = sorted[sorted.length - 1];
    const history = sorted.slice(Math.max(0, sorted.length - 4), sorted.length - 1);

    // Render history (dimmed)
    if (history.length > 0 && historyEl) {
      historyEl.innerHTML = history.map(m => {
        const name = m.speakerName || (m.speakerType === 'npc' ? 'NPC' : '你');
        const text = this._cleanResponse(m.content);
        if (!text) return '';
        return `<div class="gal-history-line"><b>${this._escHtml(name)}：</b>${this._renderContentStatic(text)}</div>`;
      }).filter(Boolean).join('');
    } else if (historyEl) {
      historyEl.innerHTML = '';
    }

    // Current message
    if (current.content) {
      const name = current.speakerName || (current.speakerType === 'npc' ? 'NPC' : '你');
      speakerEl.textContent = name;
      msgEl.innerHTML = this._renderContentStatic(this._cleanResponse(current.content));

      // Status change indicators
      if (current.speakerType === 'npc') {
        const favNum = parseInt(current.favorabilityChange) || 0;
        if (favNum !== 0) {
          const sign = favNum > 0 ? '+' : '';
          const cls = favNum < 0 ? 'negative' : 'positive';
          msgEl.innerHTML += ` <span class="msg-stat ${cls}">❤️ ${sign}${favNum}</span>`;
        }
        if (current.moodBefore && current.moodAfter && current.moodBefore !== current.moodAfter) {
          const moodEmoji = {happy:'😊', neutral:'😐', sad:'😢', angry:'😤', excited:'🤩', bored:'😴', fear:'😨'};
          const before = moodEmoji[current.moodBefore] || current.moodBefore;
          const after = moodEmoji[current.moodAfter] || current.moodAfter;
          msgEl.innerHTML += ` <span class="msg-stat mood-change">${before}→${after}</span>`;
        }
      }
    }

    // Update relationship bar from last NPC message
    const lastNpc = [...sorted].reverse().find(m => m.speakerType === 'npc');
    if (lastNpc) {
      if (lastNpc.favorabilityAfter !== undefined) {
        document.getElementById('galFavVal').textContent = lastNpc.favorabilityAfter;
      }
      if (lastNpc.familiarityAfter !== undefined) {
        document.getElementById('galFamVal').textContent = lastNpc.familiarityAfter;
      }
      if (lastNpc.moodAfter) {
        const moodStat = document.getElementById('galMoodStat');
        if (moodStat) moodStat.textContent = `${this._moodEmoji[lastNpc.moodAfter] || '😐'} ${lastNpc.moodAfter}`;
      }

      // Replay button for current NPC message
      const replayRow = document.getElementById('galReplayRow');
      if (replayRow && current.speakerType === 'npc' && current.content) {
        const hasAudio = (current._audioUrls && current._audioUrls.length > 0) ||
                         (window.ttsAudioQueue && window.ttsAudioQueue._chunkMap && window.ttsAudioQueue._chunkMap.size > 0);
        replayRow.style.display = '';
        const btn = document.getElementById('galBtnReplay');
        if (btn) {
          btn.className = 'gal-btn-replay';
          btn.textContent = '🔊 重播';
          btn.disabled = false;
          btn.onclick = () => this._replayMsgAudio(btn, current);
        }
      } else if (replayRow) {
        replayRow.style.display = 'none';
      }
    }
  },

  // ── Simple Action Bar ────────────────────────

  _renderSimpleActions() {
    const bar = document.getElementById('galActionsSimple');
    if (!bar) return;

    const npcDetail = Store.get('selectedNpcDetail');
    const relType = npcDetail?.relationship?.relationship_type || 'stranger';

    // Collect all actions from all categories, pick top unlocked ones
    const allActions = [];
    const actions = (typeof Dialogue !== 'undefined' && Dialogue) ? Dialogue._actions : {};
    for (const [cat, acts] of Object.entries(actions)) {
      if (cat === 'physical' || cat === 'negative') continue; // skip physical/negative in simple mode
      for (const a of acts) {
        const locked = a.minRel && !this._meetsRel(relType, a.minRel);
        allActions.push({ ...a, category: cat, locked });
      }
    }

    // Sort: unlocked first, by category priority (couple > intimate > friendly)
    const catOrder = { couple: 0, intimate: 1, friendly: 2 };
    allActions.sort((a, b) => {
      if (a.locked !== b.locked) return a.locked ? 1 : -1;
      return (catOrder[a.category] || 9) - (catOrder[b.category] || 9);
    });

    const top = allActions.slice(0, 5);
    bar.innerHTML = top.map(a => {
      const cls = a.locked ? 'gal-act-btn-simple locked' : 'gal-act-btn-simple';
      const title = a.locked
        ? `${a.name} — 需要关系: ${this._relCn(a.minRel)}`
        : a.name;
      return `<button class="${cls}" data-action="${a.name}" title="${title}"
               ${a.locked ? 'disabled' : ''}>${a.icon} ${a.name}</button>`;
    }).join('') + `<button class="gal-act-btn-more" id="galBtnMore" title="更多动作">··· 更多</button>`;

    // Bind click events
    bar.querySelectorAll('.gal-act-btn-simple:not(.locked)').forEach(btn => {
      btn.addEventListener('click', () => this._performAction(btn.dataset.action));
    });
    const moreBtn = document.getElementById('galBtnMore');
    if (moreBtn) moreBtn.addEventListener('click', () => this._setMode('expanded'));
  },

  // ── Expanded Action Panel ────────────────────

  _renderExpandedActions() {
    const grid = document.getElementById('galActionsGrid');
    if (!grid) return;

    const actions = ((typeof Dialogue !== 'undefined' && Dialogue) && Dialogue._actions)
      ? (Dialogue._actions[this._currentTab] || [])
      : [];
    const npcDetail = Store.get('selectedNpcDetail');
    const relType = npcDetail?.relationship?.relationship_type || 'stranger';

    grid.innerHTML = actions.map(a => {
      const locked = a.minRel && !this._meetsRel(relType, a.minRel);
      const cls = locked ? 'gal-act-btn-grid locked' : 'gal-act-btn-grid';
      const title = locked
        ? `${a.name} — 需要关系: ${this._relCn(a.minRel)}`
        : (a.attr ? `${a.name} — 需要${a.attr === 'strength' ? '力量' : '速度'}判定` : a.name);
      return `<button class="${cls}" data-action="${a.name}" title="${title}"
               ${locked ? 'disabled' : ''}>${a.icon} ${a.name}</button>`;
    }).join('');

    grid.querySelectorAll('.gal-act-btn-grid:not(.locked)').forEach(btn => {
      btn.addEventListener('click', () => this._performAction(btn.dataset.action));
    });
  },

  _setMode(mode) {
    this._mode = mode;
    document.getElementById('galActionsSimple').style.display = mode === 'simple' ? 'flex' : 'none';
    document.getElementById('galActionsExpanded').style.display = mode === 'expanded' ? 'block' : 'none';
    if (mode === 'expanded') {
      this._renderExpandedActions();
    }
  },

  // ── Send Message / Action ────────────────────

  sendMessage() {
    const input = document.getElementById('galDialogueInput');
    const npcId = Store.get('selectedNpcId');
    if (!input || !npcId) return;

    const content = input.value.trim();
    if (!content) return;

    this._allMsgs.push({
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
    this._renderTextbox(this._allMsgs);
    this._resetIdle();
  },

  _performAction(actionName) {
    const npcId = Store.get('selectedNpcId');
    if (!npcId) return;

    this._allMsgs.push({
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
    this._renderTextbox(this._allMsgs);
    this._resetIdle();
    this._setMode('simple'); // collapse to simple after action
  },

  // ── Message Handling ─────────────────────────

  _onMessagesUpdated(msgs) {
    if (!msgs || msgs.length === 0) return;
    // NPC responses come through Store (added by websocket.js).
    // Track how many Store messages we've processed to avoid duplication.
    const processed = this._storeMsgsProcessed || 0;
    if (msgs.length <= processed) return;
    const newMsgs = msgs.slice(processed);
    this._storeMsgsProcessed = msgs.length;
    for (const m of newMsgs) {
      if (m._isAmbient) continue;
      this._allMsgs.push({ ...m });
    }
    this._renderTextbox(this._allMsgs);
    this._resetIdle();
    const lastNpc = [...this._allMsgs].reverse().find(m => m.speakerType === 'npc');
    if (lastNpc && (lastNpc.favorabilityAfter !== undefined || lastNpc.familiarityAfter !== undefined)) {
      this._updateRelBarFromMsg(lastNpc);
    }
  },

  _showTyping(typing) {
    const msgEl = document.getElementById('galTextboxMsg');
    const speakerEl = document.getElementById('galTextboxSpeaker');
    if (typing) {
      const npc = Store.get('selectedNpcDetail');
      if (speakerEl) speakerEl.textContent = npc?.name || 'NPC';
      if (msgEl) msgEl.innerHTML = '<span style="opacity:0.5;font-style:italic;">正在输入...</span>';
    }
  },

  // ── Relationship Display ─────────────────────

  _updateRelDisplay(rel) {
    document.getElementById('galFavVal').textContent = rel?.favorability || 0;
    document.getElementById('galFamVal').textContent = rel?.familiarity || 0;
    document.getElementById('galRelTag').textContent = this._relCn(rel?.relationship_type || 'stranger');
  },

  _updateRelBarFromMsg(msg) {
    if (msg.favorabilityAfter !== undefined) {
      document.getElementById('galFavVal').textContent = msg.favorabilityAfter;
    }
    if (msg.familiarityAfter !== undefined) {
      document.getElementById('galFamVal').textContent = msg.familiarityAfter;
    }
    if (msg.moodAfter) {
      const moodStat = document.getElementById('galMoodStat');
      if (moodStat) moodStat.textContent = `${this._moodEmoji[msg.moodAfter] || '😐'} ${msg.moodAfter}`;
    }
  },

  // ── Audio ────────────────────────────────────

  _initCallMode() {
    const callBtn = document.getElementById('galBtnCall');
    if (!callBtn) return;
    this._inCall = false;
    this._callPhase = 'idle';

    callBtn.addEventListener('click', () => {
      this._inCall ? this._endCall() : this._startCall();
    });

    if (window.ttsAudioQueue) {
      window.ttsAudioQueue._onQueueComplete = () => {
        if (this._inCall && this._callPhase === 'speaking') {
          this._resumeCallListening();
        }
      };
    }
  },

  _startCall() {
    const npcId = Store.get('selectedNpcId');
    if (!npcId) return;
    if (!this._speechInput || !this._speechInput.supported) {
      alert('您的浏览器不支持语音识别，请使用 Chrome');
      return;
    }
    this._inCall = true;
    this._callPhase = 'listening';

    const callBtn = document.getElementById('galBtnCall');
    if (callBtn) { callBtn.textContent = '🔴 挂断'; callBtn.classList.add('in-call'); }

    const input = document.getElementById('galDialogueInput');
    if (input) { input.placeholder = '🎤 通话中...'; input.disabled = true; }
    document.getElementById('galBtnSend').disabled = true;
    const micBtn = document.getElementById('galBtnMic');
    if (micBtn) micBtn.disabled = true;

    this._showCallStatus('🎤 请说话...');

    this._speechInput._onUtteranceComplete = (text) => {
      if (!this._inCall) return;
      this._callPhase = 'processing';
      this._showCallStatus('⏳ 发送中...');
      this._sendVoiceMessage(text);
    };

    this._speechInput.startCall();
  },

  _sendVoiceMessage(text) {
    const npcId = Store.get('selectedNpcId');
    if (!npcId || !text) return;
    WSClient.send({ type: 'dialogue_send', data: { npc_id: npcId, content: text } });
    Store.addDialogue({
      speakerId: 'player', speakerName: '我', speakerType: 'player',
      content: text, gameTime: '',
    });
    this._showCallStatus('💬 等待回复...');
    this._callPhase = 'speaking';
  },

  _resumeCallListening() {
    if (!this._inCall || !this._speechInput) return;
    this._callPhase = 'listening';
    this._showCallStatus('🎤 请说话...');
    this._speechInput.resumeListening();
  },

  _endCall() {
    this._inCall = false;
    this._callPhase = 'idle';
    if (this._speechInput) this._speechInput.stopCall();

    const callBtn = document.getElementById('galBtnCall');
    if (callBtn) { callBtn.textContent = '📞 通话'; callBtn.classList.remove('in-call'); }

    const input = document.getElementById('galDialogueInput');
    if (input) { input.placeholder = '输入你想说的话...'; input.disabled = false; }
    document.getElementById('galBtnSend').disabled = false;
    const micBtn = document.getElementById('galBtnMic');
    if (micBtn) micBtn.disabled = false;

    this._hideCallStatus();
  },

  _showCallStatus(msg) {
    let status = document.getElementById('galCallStatus');
    if (!status) {
      status = document.createElement('div');
      status.id = 'galCallStatus';
      status.className = 'gal-call-status';
      const inputArea = document.querySelector('.gal-input-area');
      if (inputArea) inputArea.parentNode.insertBefore(status, inputArea);
    }
    status.textContent = msg;
    status.style.display = 'block';
  },

  _hideCallStatus() {
    const status = document.getElementById('galCallStatus');
    if (status) status.style.display = 'none';
  },

  _initSpeechInput() {
    const micBtn = document.getElementById('galBtnMic');
    if (!micBtn) return;
    const input = document.getElementById('galDialogueInput');
    if (!input) return;

    const sr = new SpeechInput({
      onResult: (result) => {
        input.value = result.final + (result.interim ? '...' : '');
      },
      onStatus: (status) => {
        if (status === 'listening') {
          micBtn.classList.add('recording');
          micBtn.textContent = '🔴';
          micBtn.title = '点击停止录音';
        } else {
          micBtn.classList.remove('recording');
          micBtn.textContent = '🎤';
          micBtn.title = '语音输入';
        }
      },
      onError: () => {
        micBtn.classList.remove('recording');
        micBtn.textContent = '🎤';
        micBtn.title = '语音输入';
      },
    });
    this._speechInput = sr;

    micBtn.addEventListener('click', () => {
      if (!sr.supported) {
        alert('您的浏览器不支持语音识别，请使用 Chrome');
        return;
      }
      if (sr.listening) {
        const text = sr.currentText.trim();
        sr.stop();
        if (text) {
          input.value = text;
          this.sendMessage();
        }
      } else {
        sr.clear();
        sr.start();
      }
    });

    if (micBtn.disabled) micBtn.disabled = false;
  },

  _toggleVoice() {
    const queue = window.ttsAudioQueue;
    if (!queue) return;
    const enabled = !queue.enabled;
    queue.setEnabled(enabled);
    document.getElementById('galBtnVoice').textContent = enabled ? '🔊' : '🔇';
    this._updateAudioIndicator();
  },

  _updateAudioIndicator() {
    const indicator = document.getElementById('galAudioIndicator');
    if (!indicator) return;
    const queue = window.ttsAudioQueue;
    const isActive = queue && queue.enabled && queue.isPlaying;
    if (isActive) {
      indicator.classList.add('active');
    } else {
      indicator.classList.remove('active');
    }
  },

  // ── Replay Audio ──────────────────────────────

  _collectAudioForMsg(m) {
    if (m._audioUrls && m._audioUrls.length > 0) return [...m._audioUrls];
    const queue = window.ttsAudioQueue;
    if (!queue || !queue._chunkMap || queue._chunkMap.size === 0) return [];
    const text = this._cleanResponse(m.content);
    if (!text) return [];
    const npcId = m.speakerId || Store.get('selectedNpcId') || '';
    const urls = [];
    for (const [chunkText, entry] of queue._chunkMap.entries()) {
      // Support both old (string URL) and new ({url, npcId}) chunkMap formats
      const url = typeof entry === 'string' ? entry : entry.url;
      const chunkNpcId = typeof entry === 'string' ? '' : (entry.npcId || '');
      // Only include chunks from this NPC, or from unknown NPC as fallback
      if (chunkNpcId && chunkNpcId !== npcId) continue;
      if (text.includes(chunkText.trim()) || chunkText.trim().includes(text.substring(0, 30))) {
        urls.push(url);
      }
    }
    return urls;
  },

  _replayMsgAudio(btn, msg) {
    if (!msg) return;
    if (btn.classList.contains('loading') || btn.classList.contains('playing')) return;

    const urls = this._collectAudioForMsg(msg);
    if (urls.length > 0) {
      this._playReplayUrls(btn, urls);
      return;
    }

    // No cached audio → request TTS generation on demand
    const npcId = msg.speakerId || Store.get('selectedNpcId');
    const text = this._cleanResponse(msg.content);
    if (!text || !npcId) {
      btn.textContent = '⏳ 无文本';
      setTimeout(() => { btn.textContent = '🔊 重播'; btn.classList.remove('loading'); }, 2000);
      return;
    }

    btn.textContent = '⏳ 生成中...';
    btn.classList.add('loading');
    btn.disabled = true;

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
      btn.disabled = false;
      if (resp && resp.status === 'ok' && resp.data && resp.data.request_id) {
        const reqId = resp.data.request_id;
        this._pendingReplayRequests[reqId] = { btn, urls: [], msg };
        setTimeout(() => {
          const pending = this._pendingReplayRequests[reqId];
          if (pending) {
            if (pending.urls.length > 0) {
              this._playReplayUrls(pending.btn, [...pending.urls]);
            } else {
              pending.btn.textContent = '⏳ 语音未就绪';
              pending.btn.classList.remove('loading');
              setTimeout(() => { if (pending.btn) pending.btn.textContent = '🔊 重播'; }, 2000);
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
      btn.disabled = false;
      btn.textContent = '⏳ 请求失败';
      btn.classList.remove('loading');
      setTimeout(() => { btn.textContent = '🔊 重播'; }, 2000);
    });
  },

  _playReplayUrls(btn, urls) {
    if (this._replayAudio) {
      this._replayAudio.pause();
      this._replayAudio = null;
    }
    if (window.ttsAudioQueue) window.ttsAudioQueue.stop();

    let idx = 0;
    btn.classList.add('playing');
    btn.classList.remove('loading');
    btn.textContent = '🔊 播放中...';
    const playNext = () => {
      if (idx >= urls.length) {
        btn.classList.remove('playing');
        btn.textContent = '🔊 重播';
        this._replayAudio = null;
        return;
      }
      this._replayAudio = new Audio(urls[idx]);
      this._replayAudio.onended = () => { idx++; playNext(); };
      this._replayAudio.onerror = () => { idx++; playNext(); };
      this._replayAudio.play().catch(() => { idx++; playNext(); });
    };
    playNext();
  },

  // ── Debug Panel ──────────────────────────────

  _toggleDebug() {
    const panel = document.getElementById('galDebugPanel');
    if (!panel) return;
    const isOpening = panel.style.display === 'none';
    if (isOpening) {
      // Refresh debug inputs from current display values
      const fav = parseInt(document.getElementById('galFavVal')?.textContent) || 0;
      const fam = parseInt(document.getElementById('galFamVal')?.textContent) || 0;
      const relTag = document.getElementById('galRelTag')?.textContent || '陌生人';
      document.getElementById('galDebugFav').value = fav;
      document.getElementById('galDebugFam').value = fam;
      const relMap = { '陌生人': 'stranger', '认识的人': 'acquaintance', '朋友': 'friend',
        '好朋友': 'best_friend', '男朋友': 'boyfriend', '女朋友': 'girlfriend',
        '配偶': 'spouse', '讨厌的人': 'dislike', '仇敌': 'enemy' };
      document.getElementById('galDebugRelType').value = relMap[relTag] || 'stranger';
    }
    panel.style.display = isOpening ? 'block' : 'none';
  },

  async _applyDebug() {
    const npcId = Store.get('selectedNpcId');
    const playerId = Store.get('playerId');
    if (!npcId) return;

    const fav = parseInt(document.getElementById('galDebugFav')?.value) || 0;
    const fam = parseInt(document.getElementById('galDebugFam')?.value) || 0;
    const relType = document.getElementById('galDebugRelType')?.value || 'stranger';

    const btn = document.getElementById('galBtnApplyDebug');
    if (btn) { btn.textContent = '...'; btn.disabled = true; }

    try {
      await API.updateNpcRelationship(npcId, playerId, {
        favorability: fav,
        familiarity: fam,
        relationship_type: relType,
      });

      // Update Store
      const detail = Store.get('selectedNpcDetail');
      if (detail?.relationship) {
        detail.relationship.favorability = fav;
        detail.relationship.familiarity = fam;
        detail.relationship.relationship_type = relType;
      }

      this._updateRelDisplay(detail?.relationship || { favorability: fav, familiarity: fam, relationship_type: relType });
      this._renderSimpleActions();
      this._renderExpandedActions();
      if (btn) btn.textContent = '✓';
    } catch (e) {
      console.error('Failed to update relationship:', e);
      if (btn) btn.textContent = '失败';
    }
    setTimeout(() => { if (btn) { btn.textContent = '应用'; btn.disabled = false; } }, 1500);
  },

  // ── Idle Timer ───────────────────────────────

  _resetIdle() {
    this._idleSeconds = 600;
    const timerEl = document.getElementById('galIdleTimer');
    const countEl = document.getElementById('galIdleCountdown');
    if (timerEl) timerEl.style.display = 'inline';

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
        this.hide();
      }
    }, 1000);
  },

  _stopIdle() {
    if (this._idleTimer) {
      clearInterval(this._idleTimer);
      this._idleTimer = null;
    }
    const timerEl = document.getElementById('galIdleTimer');
    if (timerEl) timerEl.style.display = 'none';
  },

  // ── Helpers (reuse Dialogue logic) ───────────

  _cleanResponse(text) {
    return (text || '').replace(/\[\[.*?\]\]/g, '').trim();
  },

  _renderContentStatic(text) {
    // Reuse dialogue content parsing without JSX/event handlers
    if (!text) return '';
    const segments = [];
    const re = /(「[^」]*」)|(（[^）]*）)|("[^"]*")|([^「（"]+)/g;
    let match;
    while ((match = re.exec(text)) !== null) {
      if (match[1]) {
        const inner = match[1].slice(1, -1);
        segments.push(`<span class="msg-dialogue">${this._escHtml(inner)}</span>`);
      } else if (match[2]) {
        segments.push(`<span class="msg-action">${this._escHtml(match[2])}</span>`);
      } else if (match[3]) {
        const inner = match[3].slice(1, -1);
        segments.push(`<span class="msg-dialogue">${this._escHtml(inner)}</span>`);
      } else if (match[4] && match[4].trim()) {
        segments.push(`<span class="msg-narrative">${this._escHtml(match[4])}</span>`);
      }
    }
    return segments.length > 0 ? segments.join('') : this._escHtml(text);
  },

  _escHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  },

  _meetsRel(current, required) {
    if (!(typeof Dialogue !== 'undefined' && Dialogue)) return true;
    return Dialogue._meetsRel(current, required);
  },

  _relCn(type) {
    if ((typeof Dialogue !== 'undefined' && Dialogue)) return Dialogue._relCn(type);
    const map = {
      stranger: '陌生人', acquaintance: '认识的人', friend: '朋友',
      best_friend: '好朋友', boyfriend: '男朋友', girlfriend: '女朋友',
      spouse: '配偶', parent: '父母', sibling: '兄弟姐妹', child: '子女',
      dislike: '讨厌的人', enemy: '仇敌',
    };
    return map[type] || type;
  },

  // ── History ──────────────────────────────────

  _showHistory() {
    var overlay = document.getElementById('galHistoryOverlay');
    if (!overlay) return;
    overlay.style.display = 'flex';
    var scrollEl = document.getElementById('galHistoryScroll');
    if (scrollEl) scrollEl.innerHTML = '<div class="gal-history-loading">加载中...</div>';

    var npcId = Store.get('selectedNpcId');
    if (!npcId) return;
    var playerId = Store.get('playerId');

    API.getDialogueHistory(playerId, npcId, 200).then(function(history) {
      if (!scrollEl) return;
      if (!history || history.length === 0) {
        scrollEl.innerHTML = '<div class="gal-history-empty">还没有对话记录</div>';
        return;
      }
      // Group by day
      var dayGroups = {};
      for (var i = 0; i < history.length; i++) {
        var d = history[i];
        var day = d.game_time || d.created_at || '未知时间';
        var dayKey = day.split(',')[0] || day;
        if (!dayGroups[dayKey]) dayGroups[dayKey] = [];
        dayGroups[dayKey].push(d);
      }
      var html = '';
      var dayKeys = Object.keys(dayGroups);
      for (var di = 0; di < dayKeys.length; di++) {
        var msgs = dayGroups[dayKeys[di]];
        html += '<div class="gal-history-day">' + this._escHtml(dayKeys[di]) + '</div>';
        for (var mi = 0; mi < msgs.length; mi++) {
          var m = msgs[mi];
          var isNpc = m.speaker_type === 'npc';
          var name = isNpc ? (m.speaker_name || 'NPC') : '你';
          var time = m.game_time || '';
          var text = this._cleanResponse(m.content || '');
          html += '<div class="gal-history-msg ' + (isNpc ? 'npc' : 'player') + '">'
                + '<div class="h-speaker">' + this._escHtml(name) + '<span class="h-time">' + this._escHtml(time) + '</span></div>'
                + '<div class="h-text">' + this._renderContentStatic(text) + '</div>'
                + '</div>';
        }
      }
      scrollEl.innerHTML = html;
      scrollEl.scrollTop = scrollEl.scrollHeight;
    }.bind(this)).catch(function() {
      if (scrollEl) scrollEl.innerHTML = '<div class="gal-history-empty">加载失败</div>';
    });
  },

  _hideHistory() {
    var overlay = document.getElementById('galHistoryOverlay');
    if (overlay) overlay.style.display = 'none';
  },



  // ── Scene display ────────────────────────────
  _sceneNames: {
    'scene_coffee_shop': '阳光咖啡店', 'scene_park': '中心公园', 'scene_school': '小镇高中',
    'scene_library': '公共图书馆', 'scene_market': '便民超市', 'scene_hospital': '小镇医院',
    'scene_restaurant': '小镇餐厅', 'scene_bar': '夜色酒吧', 'scene_gym': '健身中心',
    'scene_cinema': '小镇影院', 'scene_clothing': '服装店', 'scene_station': '小镇车站',
    'scene_riverside': '河边步道', 'scene_office': '镇政府', 'scene_arcade': '游戏厅',
    'apt_a': '阳光公寓A', 'apt_b': '阳光公寓B', 'apt_c': '阳光公寓C', 'apt_d': '阳光公寓D',
    'home_player': '我的公寓',
  },

  _updateSceneDisplay(npc) {
    const el = document.getElementById('galScene');
    if (!el || !npc) return;
    // ── Date lock: during a date, only update scene for the date NPC ──
    if (Dialogue._dateState && Dialogue._dateState.inDate) {
      if (npc.npc_id !== Dialogue._dateState.npcId) return;
    }
    // If NPC is in a date, show the date scene
    if (npc.in_date && npc.date_data && npc.date_data.scene_id) {
      var dateSceneId = npc.date_data.scene_id;
      var dateSceneName = this._sceneNames[dateSceneId] || dateSceneId;
      var activity = npc.date_data.activity || '约会';
      if (npc.is_traveling) {
        el.textContent = '📍 前往约会地点 → ' + dateSceneName + ' · ' + activity;
      } else {
        el.textContent = '📍 ' + dateSceneName + ' — 💕 ' + activity;
      }
      return;
    }
    // If traveling, show destination
    if (npc.is_traveling && npc.travel_target) {
      var tgtName = this._sceneNames[npc.travel_target] || npc.travel_target;
      el.textContent = '📍 前往 ' + tgtName + '…';
      return;
    }
    const sceneId = npc.current_scene_id || npc.scene_id || '';
    const sceneName = npc.current_scene_name || this._sceneNames[sceneId] || '';
    const room = npc.current_room || '';
    const act = npc.current_activity || '';
    var loc = '📍 ';
    if (sceneName) loc += sceneName;
    else if (sceneId) loc += sceneId;
    else loc += '未知';
    if (room) loc += ' · ' + room;
    if (act && act.length < 15) loc += ' — ' + act;
    el.textContent = loc;
  },

  // ── Date bar sync ────────────────────────────
  _syncDateBar() {
    console.log('[GAL] _syncDateBar called');
    if (!Dialogue._dateState) return;
    const bar = document.getElementById('galDateBar');
    console.log('[GAL] galDateBar found:', !!bar);
    if (!bar) return;
    if (Dialogue._dateState.inDate) {
      bar.style.display = 'flex';
      const textEl = document.getElementById('galDateText');
      const timeEl = document.getElementById('galDateTime');
      const phaseLabel = Dialogue._dateState.phase === 'home' ? '下半场 · NPC家中' : '上半场';
      if (textEl) textEl.textContent = phaseLabel + ' — ' + (Dialogue._dateState.activity || '约会中');
      if (timeEl) {
        if (Dialogue._dateState.phase === 'home') {
          timeEl.textContent = '自由互动';
        } else {
          timeEl.textContent = '已进行 ' + (Dialogue._dateState.elapsed || 0) + ' / ' + (Dialogue._dateState.total || 90) + ' 分钟';
        }
      }
    } else {
      bar.style.display = 'none';
    }
  },
};
