/**
 * WebSocket client with auto-reconnect.
 */
const WSClient = {
  _ws: null,
  _reconnectTimer: null,
  _url: '',

  connect(playerId) {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    this._url = `${protocol}//${location.host}/ws/game?player_id=${playerId}`;
    this._doConnect();
  },

  _doConnect() {
    if (this._ws) {
      this._ws.onclose = null;
      this._ws.close();
    }

    this._ws = new WebSocket(this._url);

    this._ws.onopen = () => {
      console.log('WebSocket connected');
      Store.set('connected', true);
    };

    this._ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this._handleMessage(msg);
      } catch (e) {
        console.error('WS parse error:', e);
      }
    };

    this._ws.onclose = () => {
      Store.set('connected', false);
      console.log('WebSocket disconnected, reconnecting in 3s...');
      this._reconnectTimer = setTimeout(() => this._doConnect(), 3000);
    };

    this._ws.onerror = (err) => {
      console.error('WebSocket error:', err);
    };
  },

  _handleMessage(msg) {
    const { type, data } = msg;
    switch (type) {
      case 'time_update':
        Store.set('gameTime', data);
        break;
      case 'weather_update':
        Store.set('weather', data);
        break;
      case 'scene_update':
        if (data.scene_id === Store.get('currentSceneId')) {
          var sd = Store.get('sceneDetail');
          if (sd) {
            sd.npcs_present = data.npcs_present;  // silent update
            // Merge home_access with room permissions (from scene_focus WS response)
            if (data.home_access) {
              sd.home_access = data.home_access;
              // Trigger re-render so room bar filters apply
              Store.set('sceneDetail', sd);
            }
            if (data.rooms) {
              sd.rooms = data.rooms;
            }
          }
        }
        break;
      case 'npc_state_update':
        Store.setNpcState(data.npc_id || data.name, data);
        /* Sync date bar if NPC is in date */
        if (data.in_date && typeof Dialogue !== 'undefined' && Dialogue._dateState) {
          var selNpcId = Store.get('selectedNpcId');
          if (data.npc_id === selNpcId) {
            var dd = data.date_data || {};
            Dialogue._dateState.inDate = true;
            Dialogue._dateState.phase = data.date_phase || 'location';
            Dialogue._dateState.elapsed = dd.elapsed || 0;
            Dialogue._dateState.total = dd.total || 90;
            Dialogue._dateState.activity = dd.activity || '';
            Dialogue._showDateBar();
            Dialogue._showDateButton(true);
          }
        }
        /* Update scene display for selected NPC */
        if (typeof Dialogue !== 'undefined' && Dialogue._updateDialogueScene) {
          var selNpcId2 = Store.get('selectedNpcId');
          if (data.npc_id === selNpcId2) {
            Dialogue._updateDialogueScene(data);
          }
        }
        if (typeof GALDialogue !== 'undefined' && GALDialogue._updateSceneDisplay) {
          var selNpcId3 = Store.get('selectedNpcId');
          if (data.npc_id === selNpcId3) {
            GALDialogue._updateSceneDisplay(data);
          }
        }
        break;
      case 'date_invite':
        /* ── Date event from server ── */
        if (data.phase === 'home_invite') {
          /* NPC invites player home */
          if (typeof Dialogue !== 'undefined' && Dialogue._showHomeInvite) {
            Dialogue._showHomeInvite(data);
          }
        } else if (data.phase === 'invite') {
          /* Date invite accepted/rejected */
          if (typeof Dialogue !== 'undefined') {
            if (data.accepted) {
              Dialogue._onDateAccepted(data);
            } else {
              Dialogue._onDateRejected(data);
            }
          }
        } else if (data.phase === 'home_invite_expired') {
          /* Backend says home invite timed out */
          if (typeof Dialogue !== 'undefined') {
            Dialogue._hideHomeInvite();
            Dialogue._clearDateState();
          }
        }
        break;
      case 'dialogue_response':
        // ── Don't let NPC-initiated greetings hijack active player dialogue ──
        var isMyDialogueNpc = (data.npc_id === Store.get('selectedNpcId'));
        // ── Date lock: during a date, only accept messages from the date NPC ──
        if (typeof Dialogue !== 'undefined' && Dialogue._dateState && Dialogue._dateState.inDate) {
          if (data.npc_id !== Dialogue._dateState.npcId && !isMyDialogueNpc) {
            // Message from non-date NPC → mark as ambient
            var ambSeq = ++Dialogue._msgSeq;
            Store.addDialogue({
              speakerId: data.npc_id, speakerName: data.npc_name, speakerType: 'npc',
              content: data.content, favorabilityChange: data.favorability_change,
              gameTime: data.game_time, _seq: ambSeq, _audioUrls: data.audio_url ? [data.audio_url] : [],
              _isAmbient: true,
            });
            break;
          }
        }

        if (data.initiated_by_npc && !isMyDialogueNpc) {
          // Greeting/social from a different NPC — silently append, don't switch NPC or stop typing
          var otherSeq = ++Dialogue._msgSeq;
          Store.addDialogue({
            speakerId: data.npc_id,
            speakerName: data.npc_name,
            speakerType: 'npc',
            content: data.content,
            favorabilityChange: data.favorability_change,
            gameTime: data.game_time,
            _seq: otherSeq,
            _audioUrls: data.audio_url ? [data.audio_url] : [],
            _isAmbient: true,
          });
          break;
        }

        // ── Normal dialogue response (from the NPC we're talking to) ──
        // Reset audio queue for the new NPC response
        if (window.ttsAudioQueue) {
          window.ttsAudioQueue._stopCurrentPlayback();
          window.ttsAudioQueue._active = true;
        }
        Store.set('isNpcTyping', false);
        var msgSeq = ++Dialogue._msgSeq;
        var pregenAudioUrl = data.audio_url || '';
        Store.addDialogue({
          speakerId: data.npc_id,
          speakerName: data.npc_name,
          speakerType: 'npc',
          content: data.content,
          favorabilityChange: data.favorability_change,
          favorabilityBefore: data.favorability_before,
          favorabilityAfter: data.favorability_after,
          familiarityAfter: data.familiarity_after,
          moodBefore: data.mood_before,
          moodAfter: data.new_mood,
          relationshipType: data.relationship_type,
          gameTime: data.game_time,
          _seq: msgSeq,
          _audioUrls: pregenAudioUrl ? [pregenAudioUrl] : [],
        });
        // Track per-NPC message seq for TTS chunk attachment (prevent cross-NPC mixing)
        if (!window._lastNpcMsgByNpc) window._lastNpcMsgByNpc = {};
        window._lastNpcMsgByNpc[data.npc_id] = { msgSeq: msgSeq, npcName: data.npc_name };
        // If pre-generated audio URL present, play it immediately
        if (pregenAudioUrl && window.ttsAudioQueue) {
          window.ttsAudioQueue.enqueue({ audio_url: pregenAudioUrl });
        }
        // Update relationship bar and mood in real-time
        if (data.favorability_after !== undefined) {
          Store.set('lastFavAfter', data.favorability_after);
        }
        if (data.favorability_change) {
          Store.set('lastFavChange', data.favorability_change);
        }
        if (data.new_mood) {
          Store.set('lastNpcMood', data.new_mood);
        }
        break;
      case 'tts_audio':
        // Check if this chunk belongs to a pending on-demand replay request
        var isReplayChunk = false;
        if (data.request_id && data.audio_url) {
          // Check both dialogue and GAL dialogue for pending replay requests
          var pending = null;
          var handler = null;
          if (GALDialogue._pendingReplayRequests && GALDialogue._pendingReplayRequests[data.request_id]) {
            pending = GALDialogue._pendingReplayRequests[data.request_id];
            handler = GALDialogue;
          } else if (Dialogue._pendingReplayRequests && Dialogue._pendingReplayRequests[data.request_id]) {
            pending = Dialogue._pendingReplayRequests[data.request_id];
            handler = Dialogue;
          }
          if (pending && handler) {
            isReplayChunk = true;
            if (!pending.urls.includes(data.audio_url)) {
              pending.urls.push(data.audio_url);
            }
            if (data.is_last) {
              handler._playReplayUrls(pending.btn, [...pending.urls]);
              delete handler._pendingReplayRequests[data.request_id];
            }
          }
        }
        // Only enqueue to real-time audio queue for non-replay chunks
        if (!isReplayChunk && window.ttsAudioQueue) {
          window.ttsAudioQueue.enqueue(data);
        }
        // Attach audio URL to the correct NPC message using per-NPC tracking
        if (window._lastNpcMsgByNpc && data.npc_id && window._lastNpcMsgByNpc[data.npc_id] && data.audio_url) {
          var npcInfo = window._lastNpcMsgByNpc[data.npc_id];
          var targetSeq = npcInfo.msgSeq;
          var msgs = Store.get('dialogueMessages');
          var targetMsg = null;
          for (var i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i]._seq === targetSeq && msgs[i].speakerId === data.npc_id) {
              targetMsg = msgs[i];
              break;
            }
          }
          if (targetMsg && targetMsg._audioUrls) {
            if (!targetMsg._audioUrls.includes(data.audio_url)) {
              targetMsg._audioUrls.push(data.audio_url);
            }
          }
        }
        break;
      case 'social_event':
        Store.addSocialEvent(data);
        break;
      case 'event_announce':
        const events = Store.get('activeEvents') || [];
        Store.set('activeEvents', [...events, data]);
        break;
      case 'pong':
        break;
      case 'home_access_denied':
        console.warn('Home access denied:', data.message);
        if (typeof Sidebar !== 'undefined' && Sidebar._handleHomeAccessDenied) {
          Sidebar._handleHomeAccessDenied(data);
        }
        break;
      case 'error':
        console.warn('Server error:', data);
        break;
      default:
        console.log('Unknown WS message type:', type);
    }
  },

  send(msg) {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(msg));
    }
  },
};
