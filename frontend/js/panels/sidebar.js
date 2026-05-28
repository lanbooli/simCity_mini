/**
 * Powers sceneBar (bottom scene quick-switch) and characterView (full-screen overlay).
 * Named "Sidebar" for backward compatibility with existing code references.
 */
const Sidebar = {
  _scenes: [],

  async init() {
    // Load scenes into bottom scene bar
    try {
      this._scenes = await API.getScenes();
      this.renderScenes();
    } catch (e) {
      console.error('Failed to load scenes:', e);
    }

    // Listen for scene updates
    Store.on('sceneDetail', () => this.renderScenes());
    Store.on('selectedNpcId', (npcId) => {
      if (npcId && App._currentView === 'character') {
        this.showNpcDetail(npcId);
      }
    });
  },

  // ── Bottom Scene Quick-Switch Bar ──────────────

  renderScenes() {
    const el = document.getElementById('sceneBar');
    if (!el) return;
    const currentScene = Store.get('currentSceneId');

    // Group: public scenes first, then residential (home) scenes
    const publicScenes = this._scenes.filter(s => s.scene_type !== 'home');
    const homeScenes = this._scenes.filter(s => s.scene_type === 'home');

    const renderBtn = (s) => {
      const active = s.id === currentScene ? ' active' : '';
      const isHome = s.scene_type === 'home';
      const homeIcon = isHome ? (s.id === 'home_player' ? ' 🏠' : ' 🏢') : '';
      return `<button class="scene-bar-btn${active}${isHome ? ' scene-home-btn' : ''}" data-scene-id="${s.id}">
        <span>${s.icon || '📍'}</span>
        <span>${s.name}${homeIcon}</span>
      </button>`;
    };

    let html = publicScenes.map(renderBtn).join('');
    if (homeScenes.length) {
      html += '<span class="scene-bar-divider"></span>';
      html += homeScenes.map(renderBtn).join('');
    }
    el.innerHTML = html;

    // Event delegation
    el.querySelectorAll('.scene-bar-btn').forEach(btn => {
      btn.addEventListener('click', () => this.selectScene(btn.dataset.sceneId));
    });
  },

  async selectScene(sceneId) {
    const prevSceneId = Store.get('currentSceneId');
    Store.set('currentSceneId', sceneId);
    this.renderScenes();

    try {
      // Send scene_focus via WebSocket for backend location tracking + permission check
      WSClient.send({ type: 'scene_focus', data: { scene_id: sceneId } });
      const detail = await API.getScene(sceneId);
      Store.set('sceneDetail', detail);
    } catch (e) {
      console.error('Failed to load scene:', e);
      // Revert on error
      Store.set('currentSceneId', prevSceneId);
      this.renderScenes();
    }
  },

  _handleHomeAccessDenied(data) {
    const msg = data.message || '你和TA还不够熟悉，不便打扰';
    if (typeof App !== 'undefined' && App.showToast) {
      App.showToast(msg, 'warning');
    } else {
      alert(msg);
    }
  },

  // ── Character View (full-screen overlay) ────────

  async showNpcDetail(npcId) {
    const content = document.getElementById('characterContent');
    if (!content) return;

    if (!npcId) {
      content.innerHTML = '<div class="empty-hint">点击NPC查看详情</div>';
      Store.set('selectedNpcId', null);
      return;
    }

    Store.set('selectedNpcId', npcId);
    content.innerHTML = '<div class="empty-hint">加载中...</div>';

    try {
      const npc = await API.getNpc(npcId);
      const rel = await API.getNpcRelationship(npcId, Store.get('playerId'));
      content.innerHTML = this._renderCharacterCard(npc, rel);
    } catch (e) {
      content.innerHTML = '<div class="empty-hint">加载NPC信息失败</div>';
      console.error('Failed to load NPC detail:', e);
    }
  },

  _renderCharacterCard(npc, rel) {
    const personality = Array.isArray(npc.personality) ? npc.personality : [];
    const appearance = npc.appearance || {};
    const clothing = npc.clothing || {};
    const goals = npc.goals || [];

    const npcState = Store.get('npcs')?.[npc.id] || {};
    const aa = npcState.auto_action;
    const currentActionHtml = aa
      ? `<span style="color:var(--mood-happy);">${aa.icon || ''} ${aa.display_text || aa.action_name || ''}</span>`
      : (npcState.current_activity || npc.current_activity || '闲逛中');

    const avatarUrl = npc.appearance?.avatar || npc.avatar || '';
    const genderEmoji = npc.gender === 'male' ? '👦' : npc.gender === 'female' ? '👧' : '🧑';
    const animClass = aa?.animation ? `css-${aa.animation}` : '';

    // Build persona text
    const personaParts = [];
    if (npc.age) personaParts.push(`${npc.age}岁`);
    personaParts.push(npc.gender === 'male' ? '♂' : npc.gender === 'female' ? '♀' : '⚧');
    if (npc.career) personaParts.push(npc.career);
    const personaText = personaParts.join(' · ');

    return `
      <div class="char-card">
        <div class="char-avatar-wrap">
          ${avatarUrl
            ? `<img src="${avatarUrl}" class="char-avatar-img" alt="${npc.name}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">`
            : ''}
          <div class="char-avatar-emoji ${animClass}" style="${avatarUrl ? 'display:none;' : ''}font-size:64px;">${genderEmoji}</div>
        </div>
        <div class="char-name">${npc.name}</div>
        <div class="char-bio">${personaText}</div>
        <div class="char-current">当前：${currentActionHtml}</div>

        <div class="char-section">
          <div class="char-section-title">外貌</div>
          <div class="char-section-text">${Object.entries({...appearance, ...clothing}).map(([k,v]) => `${k}: ${v}`).join(', ') || '暂无信息'}</div>
        </div>

        <div class="char-section">
          <div class="char-section-title">性格</div>
          <div class="personality-tags">
            ${personality.map(p => `<span class="personality-tag">${p}</span>`).join('') || '暂无'}
          </div>
        </div>

        <div class="char-section">
          <div class="char-section-title">💕 与你的关系</div>
          <div class="char-section-text">
            ${rel.relationship_type ? `关系: ${rel.relationship_type}<br>` : ''}
            ${typeof renderRelationshipBars !== 'undefined' ? renderRelationshipBars(rel.favorability || 0, rel.familiarity || 0) : ''}
          </div>
        </div>

        ${goals.length ? `
        <div class="char-section">
          <div class="char-section-title">🎯 近期目标</div>
          <div class="char-section-text">
            ${goals.map(g => `• [${g.goal_type || '目标'}] ${g.description || ''}`).join('<br>')}
          </div>
        </div>` : ''}

        <div class="char-section">
          <div class="char-section-title">📍 所在位置</div>
          <div class="char-section-text">${_formatLocation(npc, npcState)}</div>
        </div>

        <button class="char-btn-dialogue" onclick="App.selectNpc('${npc.id}')">💬 开始对话</button>
      </div>`;
  },
};

/** Format location string for character card: "场景名 · 房间" or "场景名" */
function _formatLocation(npc, npcState) {
  const sceneName = npcState.current_scene_name || npc.scene_name || '未知';
  const roomName = npcState.current_room || '';
  if (roomName) {
    return `${sceneName} · ${roomName}`;
  }
  return sceneName;
}
