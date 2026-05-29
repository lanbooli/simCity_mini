/**
 * Powers sceneBar (bottom scene quick-switch) and characterView (full-screen overlay).
 */
const Sidebar = {
  _scenes: [],
  _cat: null,  // current category: 'public' | 'home' | null

  // Scene icon mapping
  _icons: {
    scene_coffee_shop:'\u2615', scene_park:'\ud83c\udf33', scene_school:'\ud83c\udfeb',
    scene_library:'\ud83d\udcda', scene_market:'\ud83d\udecd', scene_hospital:'\ud83c\udfe5',
    scene_restaurant:'\ud83c\udf7d', scene_bar:'\ud83c\udf78', scene_gym:'\ud83c\udfcb',
    scene_cinema:'\ud83c\udfac', scene_clothing:'\ud83d\udc57', scene_station:'\ud83d\ude89',
    scene_riverside:'\ud83c\udf0a', scene_office:'\ud83c\udfdb', scene_arcade:'\ud83c\udfae',
    apt_a:'\ud83c\udfe2', apt_b:'\ud83c\udfe2', apt_c:'\ud83c\udfe2', apt_d:'\ud83c\udfe2',
    home_player:'\ud83c\udfe0',
  },

  async init() {
    try {
      this._scenes = await API.getScenes();
      this.renderSceneBar();
    } catch (e) {
      console.error('Failed to load scenes:', e);
    }
    Store.on('sceneDetail', () => this.renderSceneBar());
    Store.on('selectedNpcId', (npcId) => {
      if (npcId && App._currentView === 'character') this.showNpcDetail(npcId);
    });
  },

  // ── Scene Bar (two-row) ──

  renderSceneBar() {
    this._renderCatRow();
    this._renderBtnRow();
  },

  _renderCatRow() {
    const el = document.getElementById('sceneCatRow');
    if (!el) return;
    const currentId = Store.get('currentSceneId');
    const currentScene = this._scenes.find(s => s.id === currentId);
    const currentName = currentScene ? currentScene.name : '';
    const cat = this._cat;

    el.innerHTML =
      '<button class="scene-cat-btn' + (cat === 'public' ? ' active' : '') + '" data-cat="public">\ud83c\udfd9\ufe0f 公共场所</button>' +
      '<button class="scene-cat-btn' + (cat === 'home' ? ' active' : '') + '" data-cat="home">\ud83c\udfe0 住宅</button>' +
      '<span class="scene-cat-current">\ud83d\udccd ' + currentName + '</span>' +
      '<button class="scene-map-btn" onclick="Sidebar.openMap()">\ud83d\uddfa\ufe0f 地图</button>';

    el.querySelectorAll('.scene-cat-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const newCat = btn.dataset.cat;
        this._cat = (this._cat === newCat) ? null : newCat;
        this._renderCatRow();
        this._renderBtnRow();
      });
    });
  },

  _renderBtnRow() {
    const el = document.getElementById('sceneBtnRow');
    if (!el) return;
    const currentId = Store.get('currentSceneId');
    const cat = this._cat;

    let scenes = this._scenes;
    if (cat === 'public') scenes = scenes.filter(s => s.scene_type !== 'home');
    else if (cat === 'home') scenes = scenes.filter(s => s.scene_type === 'home');

    el.innerHTML = scenes.map(s => {
      const icon = this._icons[s.id] || '\ud83d\udccd';
      const active = s.id === currentId ? ' active' : '';
      return '<button class="scene-bar-btn' + active + '" data-scene-id="' + s.id + '" data-tooltip="' + s.name + '">' + icon + '</button>';
    }).join('');

    el.querySelectorAll('.scene-bar-btn').forEach(btn => {
      btn.addEventListener('click', () => this.selectScene(btn.dataset.sceneId));
    });

    // Scroll current into view
    const curBtn = el.querySelector('.scene-bar-btn.active');
    if (curBtn) curBtn.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  },

  async selectScene(sceneId) {
    const prevSceneId = Store.get('currentSceneId');
    Store.set('currentSceneId', sceneId);
    this.renderSceneBar();
    try {
      WSClient.send({ type: 'scene_focus', data: { scene_id: sceneId } });
      const detail = await API.getScene(sceneId);
      Store.set('sceneDetail', detail);
    } catch (e) {
      console.error('Failed to load scene:', e);
      Store.set('currentSceneId', prevSceneId);
      this.renderSceneBar();
    }
  },

  // ── Map Overlay ──

  openMap() {
    const overlay = document.getElementById('sceneMapOverlay');
    const grid = document.getElementById('sceneMapGrid');
    if (!overlay || !grid) return;
    const currentId = Store.get('currentSceneId');
    const npcState = Store.get('npcs') || {};

    grid.innerHTML = this._scenes.map(s => {
      const icon = this._icons[s.id] || '\ud83d\udccd';
      const isCurrent = s.id === currentId;
      let npcCount = 0;
      for (const [nid, ns] of Object.entries(npcState)) {
        if (ns.current_scene_id === s.id) npcCount++;
      }
      const npcText = npcCount > 0 ? '\ud83d\udc64 ' + npcCount + '人' : '';
      return '<div class="scene-map-card' + (isCurrent ? ' current' : '') + '" data-scene-id="' + s.id + '">' +
        '<span class="scene-map-icon">' + icon + '</span>' +
        '<span class="scene-map-name">' + s.name + '</span>' +
        (npcText ? '<span class="scene-map-npc">' + npcText + '</span>' : '') +
        '</div>';
    }).join('');

    grid.querySelectorAll('.scene-map-card').forEach(card => {
      card.addEventListener('click', () => {
        this.selectScene(card.dataset.sceneId);
        this.closeMap();
      });
    });

    overlay.style.display = 'flex';
  },

  closeMap() {
    const overlay = document.getElementById('sceneMapOverlay');
    if (overlay) overlay.style.display = 'none';
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
      ? '<span style="color:var(--mood-happy);">' + (aa.icon || '') + ' ' + (aa.display_text || aa.action_name || '') + '</span>'
      : (npcState.current_activity || npc.current_activity || '闲逛中');

    const avatarUrl = npc.appearance?.avatar || npc.avatar || '';
    const genderEmoji = npc.gender === 'male' ? '\ud83d\udc66' : npc.gender === 'female' ? '\ud83d\udc67' : '\ud83e\uddd1';
    const animClass = aa?.animation ? 'css-' + aa.animation : '';

    const personaParts = [];
    if (npc.age) personaParts.push(npc.age + '岁');
    personaParts.push(npc.gender === 'male' ? '♂' : npc.gender === 'female' ? '♀' : '⚧');
    if (npc.career) personaParts.push(npc.career);
    const personaText = personaParts.join(' · ');

    return '<div class="char-card">' +
      '<div class="char-avatar-wrap">' +
        (avatarUrl ? '<img src="' + avatarUrl + '" class="char-avatar-img" alt="' + npc.name + '" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">' : '') +
        '<div class="char-avatar-emoji ' + animClass + '" style="' + (avatarUrl ? 'display:none;' : '') + 'font-size:64px;">' + genderEmoji + '</div>' +
      '</div>' +
      '<div class="char-name">' + npc.name + '</div>' +
      '<div class="char-bio">' + personaText + '</div>' +
      '<div class="char-current">当前：' + currentActionHtml + '</div>' +
      '<div class="char-section"><div class="char-section-title">外貌</div><div class="char-section-text">' + (Object.entries({...appearance, ...clothing}).map(([k,v]) => k + ': ' + v).join(', ') || '暂无信息') + '</div></div>' +
      '<div class="char-section"><div class="char-section-title">性格</div><div class="personality-tags">' + (personality.map(p => '<span class="personality-tag">' + p + '</span>').join('') || '暂无') + '</div></div>' +
      '<div class="char-section"><div class="char-section-title">\ud83d\udc95 与你的关系</div><div class="char-section-text">' +
        (rel.relationship_type ? '关系: ' + rel.relationship_type + '<br>' : '') +
        (typeof renderRelationshipBars !== 'undefined' ? renderRelationshipBars(rel.favorability || 0, rel.familiarity || 0) : '') +
      '</div></div>' +
      (goals.length ? '<div class="char-section"><div class="char-section-title">\ud83c\udfaf 近期目标</div><div class="char-section-text">' + goals.map(g => '• [' + (g.goal_type || '目标') + '] ' + (g.description || '')).join('<br>') + '</div></div>' : '') +
      '<div class="char-section"><div class="char-section-title">\ud83d\udccd 所在位置</div><div class="char-section-text">' + _formatLocation(npc, npcState) + '</div></div>' +
      '<button class="char-btn-dialogue" onclick="App.selectNpc(\'' + npc.id + '\')">\ud83d\udcac 开始对话</button>' +
      '</div>';
  },
};

/** Format location string for character card */
function _formatLocation(npc, npcState) {
  const sceneName = npcState.current_scene_name || npc.scene_name || '未知';
  const roomName = npcState.current_room || '';
  if (roomName) return sceneName + ' · ' + roomName;
  return sceneName;
}
