/**
 * Player settings panel - detail view + edit view.
 */
const PlayerSettings = {
  _visible: false,
  _playerData: null,
  _relationships: [],
  _currentTab: 'detail',
  _saving: false,

  init() {
    document.getElementById('btnPlayerSettings')?.addEventListener('click', () => this.toggle());
    document.getElementById('btnPlayerSettingsClose')?.addEventListener('click', () => this.hide());
    document.getElementById('btnPlayerSettingsSave')?.addEventListener('click', () => this._save());

    // Tab switching
    document.getElementById('psTabs')?.addEventListener('click', (e) => {
      const tab = e.target.closest('.ps-tab');
      if (!tab) return;
      this._switchTab(tab.dataset.tab);
    });

    // Overlay click to close
    document.getElementById('playerSettingsOverlay')?.addEventListener('click', (e) => {
      if (e.target === e.currentTarget && !this._saving) this.hide();
    });

    // Escape to close (only when not typing)
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || !this._visible || this._saving) return;
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      this.hide();
    });
  },

  async toggle() {
    this._visible ? this.hide() : await this.show();
  },

  async show() {
    const overlay = document.getElementById('playerSettingsOverlay');
    if (!overlay) return;
    this._visible = true;
    this._openTime = Date.now();
    overlay.style.display = 'flex';
    this._switchTab('detail');

    const playerId = Store.get('playerId');
    try {
      const [player, rels] = await Promise.all([
        API.getPlayer(playerId),
        API.getPlayerRelationships(playerId),
      ]);
      this._playerData = player;
      this._relationships = rels || [];
      this._renderDetail();
      this._populateEditForm(player);
    } catch (e) {
      console.error('Failed to load player data:', e);
      this._playerData = null;
      this._relationships = [];
      this._renderDetail();
      this._populateEditForm(null);
    }
  },

  hide() {
    // Don't close if: saving, editing, or just opened (<500ms)
    if (this._saving || this._currentTab === 'edit') return;
    if (this._openTime && Date.now() - this._openTime < 500) return;
    this._visible = false;
    this._openTime = 0;
    const overlay = document.getElementById('playerSettingsOverlay');
    if (overlay) overlay.style.display = 'none';
  },

  _switchTab(tab) {
    this._currentTab = tab;
    document.querySelectorAll('.ps-tab').forEach(t => {
      t.classList.toggle('active', t.dataset.tab === tab);
    });
    document.getElementById('psDetailView').style.display = tab === 'detail' ? '' : 'none';
    document.getElementById('psEditView').style.display = tab === 'edit' ? '' : 'none';
    document.getElementById('psTitle').textContent = tab === 'detail' ? '👤 个人信息' : '✏️ 编辑资料';
  },

  // ── Detail View ───────────────────────────

  _renderDetail() {
    const p = this._playerData;
    const card = document.getElementById('psProfileCard');
    if (!card) return;

    if (!p) {
      card.innerHTML = '<div class="empty-hint">加载失败</div>';
      return;
    }

    // Parse appearance
    let appearance = p.appearance || {};
    if (typeof appearance === 'string') {
      try { appearance = JSON.parse(appearance); } catch(e) { appearance = {}; }
    }
    const appStr = Object.values(appearance).join(' · ') || '未设置';

    // Parse personality
    let personality = p.personality || [];
    if (typeof personality === 'string') {
      try { personality = JSON.parse(personality); } catch(e) { personality = []; }
    }

    // Calculate age
    let age = '?';
    try { age = 2026 - parseInt((p.birth_date || '2000').split('-')[0]); } catch(e) {}

    const genderMap = { male: '♂ 男', female: '♀ 女', other: '⚧ 其他' };

    card.innerHTML = `
      <div class="ps-profile-name">${p.name || '玩家'}</div>
      <div class="ps-profile-tags">
        ${personality.map(t => `<span class="ps-profile-tag">${t}</span>`).join('')}
      </div>
      <div class="ps-profile-detail">
        ${genderMap[p.gender || 'other']} · ${age}岁 · ${p.career || '小镇居民'}<br>
        外貌：${appStr}
      </div>`;

    // Render relationship list
    this._renderRelList();
  },

  _renderRelList() {
    const el = document.getElementById('psRelList');
    if (!el) return;

    if (!this._relationships.length) {
      el.innerHTML = '<div class="empty-hint">暂无关系数据</div>';
      return;
    }

    const relCn = t => ({
      stranger:'陌生人', acquaintance:'认识的人', friend:'朋友', best_friend:'好朋友',
      boyfriend:'男朋友', girlfriend:'女朋友', spouse:'配偶',
      dislike:'讨厌的人', enemy:'仇敌',
      parent:'父母', sibling:'兄弟姐妹', child:'子女',
    }[t] || t);

    // Sort by |favorability| descending
    const sorted = [...this._relationships].sort((a, b) => Math.abs(b.favorability||0) - Math.abs(a.favorability||0));

    el.innerHTML = sorted.map(r => {
      const name = r.entity_b_name || r.entity_b_id || '?';
      const npcId = r.entity_b_id || '';
      const fav = r.favorability || 0;
      const fam = r.familiarity || 0;
      const favColor = fav >= 0 ? 'var(--accent-pink)' : 'var(--mood-angry)';
      return `
        <div class="ps-rel-item" data-npc-id="${npcId}" onclick="PlayerSettings._openNpc('${npcId}')">
          <div class="ps-rel-left">
            <span class="ps-rel-npc-name">${name}</span>
            <span class="ps-rel-type">${relCn(r.relationship_type)}</span>
          </div>
          <div class="ps-rel-right">
            <span class="ps-rel-stat" style="color:${favColor}">❤️ ${fav}</span>
            <span class="ps-rel-stat">👋 ${fam}</span>
            <span class="ps-rel-arrow">›</span>
          </div>
        </div>`;
    }).join('');
  },

  _openNpc(npcId) {
    if (!npcId) return;
    // Close player panel and select the NPC
    this.hide();
    if (typeof App !== 'undefined' && App.selectNpc) {
      App.selectNpc(npcId);
    }
    // Also open social circle NPC detail
    if (typeof SocialCircle !== 'undefined' && SocialCircle._selectNpc) {
      const btnSocial = document.getElementById('btnSocialCircle');
      if (btnSocial) btnSocial.click();
      setTimeout(() => SocialCircle._selectNpc(npcId), 300);
    }
  },

  // ── Edit View ─────────────────────────────

  _populateEditForm(data) {
    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.value = val;
    };

    setVal('psName', data?.name || '玩家');
    setVal('psBirthDate', data?.birth_date || '2000-01-01');
    setVal('psGender', data?.gender || 'other');

    let appearance = data?.appearance || {};
    if (typeof appearance === 'string') {
      try { appearance = JSON.parse(appearance); } catch(e) { appearance = {}; }
    }
    ['height', 'build', 'hair', 'eyes', 'skin'].forEach(k => {
      setVal('psApp_' + k, appearance[k] || '');
    });

    let personality = data?.personality || [];
    if (typeof personality === 'string') {
      try { personality = JSON.parse(personality); } catch(e) { personality = []; }
    }
    setVal('psPersonality', Array.isArray(personality) ? personality.join('，') : (personality || ''));

    setVal('psCareer', data?.career || '');

    // Show existing images
    const avatarPreview = document.getElementById('psAvatarPreview');
    const fullbodyPreview = document.getElementById('psFullbodyPreview');
    if (avatarPreview && appearance.avatar) {
      avatarPreview.innerHTML = `<img src="${appearance.avatar}" style="max-width:60px;max-height:60px;border-radius:4px;">`;
    }
    if (fullbodyPreview && appearance.fullbody) {
      fullbodyPreview.innerHTML = `<img src="${appearance.fullbody}" style="max-width:60px;max-height:80px;border-radius:4px;">`;
    }
  },

  async _uploadImage(file) {
    // Upload image via API and return the URL
    const formData = new FormData();
    formData.append('file', file);
    try {
      const resp = await fetch('/api/upload', { method: 'POST', body: formData });
      const json = await resp.json();
      if (json.url) return json.url;
    } catch (e) {
      console.error('Upload failed:', e);
    }
    return null;
  },

  async _save() {
    if (this._saving) return;
    this._saving = true;

    const getVal = (id) => document.getElementById(id)?.value?.trim() || '';

    const appearance = {};
    ['height', 'build', 'hair', 'eyes', 'skin'].forEach(k => {
      const v = getVal('psApp_' + k);
      if (v) appearance[k] = v;
    });

    // Handle image uploads: read as data URL for simplicity
    const avatarFile = document.getElementById('psAvatarUpload')?.files?.[0];
    const fullbodyFile = document.getElementById('psFullbodyUpload')?.files?.[0];

    // Upload files via API if selected
    if (avatarFile) {
      const url = await this._uploadImage(avatarFile);
      if (url) appearance.avatar = url;
    }
    if (fullbodyFile) {
      const url = await this._uploadImage(fullbodyFile);
      if (url) appearance.fullbody = url;
    }

    const personalityStr = getVal('psPersonality');
    const personality = personalityStr
      ? personalityStr.split(/[,，、\s]+/).filter(Boolean)
      : [];

    const data = {
      name: getVal('psName'),
      birth_date: getVal('psBirthDate'),
      gender: getVal('psGender'),
      appearance: appearance,
      personality: personality,
      career: getVal('psCareer'),
    };

    const btn = document.getElementById('btnPlayerSettingsSave');
    const origText = btn.textContent;
    btn.textContent = '保存中...';
    btn.disabled = true;

    try {
      const playerId = Store.get('playerId');
      const updated = await API.updatePlayer(playerId, data);
      this._playerData = updated;
      Store.set('playerData', updated);
      this._renderDetail();
      btn.textContent = '✓ 已保存';
      setTimeout(() => {
        btn.textContent = origText;
        btn.disabled = false;
        this._saving = false;
        this._switchTab('detail');
      }, 800);
    } catch (e) {
      console.error('Failed to update player:', e);
      btn.textContent = '保存失败';
      btn.disabled = false;
      this._saving = false;
      setTimeout(() => { btn.textContent = origText; }, 2000);
    }
  },
};
