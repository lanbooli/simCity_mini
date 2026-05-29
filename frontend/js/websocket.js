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
        break;
      case 'dialogue_response':
        // NPC-initiated greeting: auto-select NPC if none selected
        if (data.npc_id !== Store.get('selectedNpcId')) {
          if (data.initiated_by_npc && typeof App !== 'undefined' && App.selectNpc) {
            App.selectNpc(data.npc_id);
            // Fall through to Store.addDialogue so text appears immediately
          } else {
            break;  // Different NPC, not initiated by NPC — ignore
          }
        }
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
          _audioUrls: pregenAudioUrl ? [pregenAudioUrl] : [],  // pre-generated greeting audio
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
