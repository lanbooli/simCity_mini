/**
 * Panel 3: Scene view - current scene with NPCs and items.
 * For home scenes, renders a room selection bar with NPC/item filtering.
 */
const SceneView = {
  _bubbleTimers: {},
  _selectedRoom: '',  // currently selected room (empty = show all)

  init() {
    Store.on('sceneDetail', (detail) => this.render(detail));
    Store.on('npcs', () => {
      const detail = Store.get('sceneDetail');
      if (detail) this.render(detail);
    });
    Store.on('currentSceneId', async (sceneId) => {
      // Clear room selection when switching scenes
      this._selectedRoom = '';
      try {
        const detail = await API.getScene(sceneId);
        Store.set('sceneDetail', detail);
      } catch (e) {
        console.error('Failed to load scene:', e);
      }
    });

    // Listen for social events to show bubbles
    Store.on('socialBubbles', (bubbles) => this._updateBubbles(bubbles));

    // Load initial scene
    const initialScene = Store.get('currentSceneId');
    if (initialScene) {
      API.getScene(initialScene).then(d => Store.set('sceneDetail', d)).catch(() => {});
    }
  },

  selectRoom(roomName) {
    this._selectedRoom = this._selectedRoom === roomName ? '' : roomName;
    const detail = Store.get('sceneDetail');
    if (detail) this.render(detail);
  },

  render(detail) {
    if (!detail) return;

    const isHome = detail.scene_type === 'home';
    const rooms = detail.rooms || [];

    // Scene header
    const header = document.getElementById('sceneHeader');
    if (header) {
      header.innerHTML = `
        <h2>${detail.icon || '📍'} ${detail.name}</h2>
        <p class="scene-desc">${detail.description || ''}</p>`;
    }

    // ── Room selection bar (home scenes only) ──
    const roomBar = document.getElementById('roomBar');
    if (roomBar) {
      if (isHome && rooms.length > 0) {
        roomBar.style.display = 'flex';
        const self = this;
        // Build room buttons with access info from home_access
        const hasAccessData = detail.home_access && detail.home_access.rooms;
        const visibleRooms = rooms.filter(r => {
          if (!hasAccessData) return r.access !== 'private';  // fallback
          const ar = detail.home_access.rooms.find(ar => ar.name === r.name);
          if (!ar || !ar.can_enter) {
            // Hide private bedrooms the player can't access; show occupied public rooms
            return r.access !== 'private';
          }
          return true;
        });
        if (visibleRooms.length === 0) {
          roomBar.style.display = 'none';
          roomBar.innerHTML = '';
        } else {
          roomBar.innerHTML = visibleRooms.map(r => {
            const active = self._selectedRoom === r.name ? ' active' : '';
            let disabled = '';
            let label = '';
            if (hasAccessData) {
              const ar = detail.home_access.rooms.find(ar => ar.name === r.name);
              if (ar && !ar.can_enter) {
                disabled = ' disabled';
                label = ' 🚿使用中';  // public room occupied (bathroom)
              } else if (r.access === 'private') {
                label = ' 🔒';
              }
            } else if (r.access === 'private') {
              label = ' 🔒';
            }
            return `<button class="room-bar-btn${active}${disabled}" data-room="${r.name}"${disabled ? ' disabled' : ''}>
              <span>${r.icon || '🚪'}</span>
              <span>${r.name}${label}</span>
            </button>`;
          }).join('');
          roomBar.querySelectorAll('.room-bar-btn:not([disabled])').forEach(btn => {
            btn.addEventListener('click', () => this.selectRoom(btn.dataset.room));
          });
        }
      } else {
        roomBar.style.display = 'none';
        roomBar.innerHTML = '';
      }
    }

    // ── NPC grid ──
    const grid = document.getElementById('npcGrid');
    if (grid && detail.npcs) {
      const npcState = Store.get('npcs') || {};
      const bubbles = Store.get('socialBubbles') || {};
      const selectedRoom = this._selectedRoom;
      const npcs = detail.npcs.map(n => {
        const state = npcState[n.id] || {};
        const isSleeping = state.is_sleeping || false;
        const activity = (isSleeping ? '😴 ' : '') + (state.current_activity || n.current_activity || '闲逛中');
        const roomName = state.current_room || '';
        return {
          id: n.id,
          name: n.name,
          gender: n.gender,
          career: n.career || '',
          mood: state.mood || n.current_mood || 'neutral',
          activity: activity,
          roomName: roomName,
          role: n.role === 'worker' ? '工作人员' : (n.role === 'resident' ? '住户' : '访客'),
          avatar: n.avatar || '',
          is_sleeping: state.is_sleeping || false,
          in_dialogue: state.in_dialogue || false,
          bubble: bubbles[n.id] || null,
          auto_action: state.auto_action || null,
        };
      });

      // Filter by selected room (NPCs whose activity contains room name or whose room matches)
      const filtered = selectedRoom
        ? npcs.filter(n => n.roomName && n.roomName.includes(selectedRoom))
        : npcs;

      if (filtered.length === 0 && selectedRoom) {
        grid.innerHTML = `<div class="empty-hint">${selectedRoom}里没有人</div>`;
      } else {
        grid.innerHTML = filtered.map(n => renderNpcCard(n)).join('');
      }
    }

    // ── Items bar (grouped by room for home scenes) ──
    const itemsBar = document.getElementById('itemsBar');
    if (itemsBar && detail.items) {
      const selectedRoom = this._selectedRoom;
      let items = detail.items || [];
      if (selectedRoom && isHome) {
        items = items.filter(i => i.room_name && i.room_name.includes(selectedRoom));
      }
      const tags = items.map(i => {
        const funcLabel = i.function ? ` [${i.function}]` : '';
        return `<span class="item-tag" title="${i.description || ''}${funcLabel}">${i.name}</span>`;
      }).join('');
      itemsBar.innerHTML = `<span class="items-label">📦 道具:</span>${tags || ' 暂无'}`;
    }

    this._updateBubbles(Store.get('socialBubbles') || {});
  },

  _updateBubbles(bubbles) {
    if (!bubbles) return;

    for (const [npcId, bubble] of Object.entries(bubbles)) {
      const card = document.querySelector(`.npc-card[data-npc-id="${npcId}"]`);
      if (!card) continue;

      // Remove existing bubble
      const existing = card.querySelector('.npc-social-bubble');
      if (existing) existing.remove();

      // Create new bubble
      const bubbleEl = document.createElement('div');
      bubbleEl.className = 'npc-social-bubble';
      bubbleEl.style.cursor = 'pointer';
      bubbleEl.title = '点击查看NPC详情';
      bubbleEl.addEventListener('click', (e) => { e.stopPropagation(); App.selectNpc(npcId); });

      const isIntimate = bubble.actionName && ['hug', 'kiss', 'cheek_kiss', 'sweet_talk', 'cuddle'].includes(bubble.actionName);
      const isInnerThought = bubble.phase === 'inner_thought';
      const isNpcAction = bubble.phase === 'npc_action';
      const isAutoAction = bubble.phase === 'auto_action';

      if (isAutoAction) {
        bubbleEl.classList.add('auto-action-bubble');
        bubbleEl.classList.add(ActionRenderer.getBubbleClass(bubble.category || 'solo'));
        bubbleEl.textContent = `${bubble.icon || ''} ${bubble.content}`.trim();
      } else if (isInnerThought) {
        bubbleEl.classList.add('thought-bubble');
        bubbleEl.textContent = bubble.content;
      } else if (isIntimate) {
        bubbleEl.classList.add('intimate-bubble');
        bubbleEl.textContent = `💕 ${bubble.content}`;
      } else if (isNpcAction) {
        bubbleEl.classList.add('action-bubble');
        bubbleEl.textContent = `✨ ${bubble.content}`;
      } else {
        bubbleEl.classList.add('social-bubble');
        bubbleEl.textContent = `💬 ${bubble.content}`;
      }

      card.appendChild(bubbleEl);

      // Auto-remove based on action duration (1 tick ≈ 1500ms, min 3s max 15s)
      const durationMs = Math.min(Math.max((bubble.durationTicks || 3) * 1500, 3000), 15000);
      const bubbleId = bubble.id;
      if (this._bubbleTimers[bubbleId]) clearTimeout(this._bubbleTimers[bubbleId]);
      this._bubbleTimers[bubbleId] = setTimeout(() => {
        if (bubbleEl.parentNode) bubbleEl.remove();
        Store.clearSocialBubble(npcId);
        delete this._bubbleTimers[bubbleId];
      }, durationMs);
    }
  },
};
