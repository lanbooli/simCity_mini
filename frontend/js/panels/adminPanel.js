/**
 * Admin Panel — Hidden floating panel for testing (Ctrl+Shift+M or ?admin=true).
 */
const AdminPanel = {
  _visible: false,
  _selectedNpcId: null,

  init() {
    // Check URL param
    if (window.location.search.includes('admin=true')) {
      this._visible = true;
    }

    document.addEventListener('keydown', (e) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'M') {
        e.preventDefault();
        this.toggle();
      }
    });

    this._render();
  },

  toggle() {
    this._visible = !this._visible;
    const el = document.getElementById('adminPanel');
    if (el) el.style.display = this._visible ? 'flex' : 'none';
    if (this._visible) this._refreshAll();
  },

  _render() {
    const html = `
    <div id="adminPanel" style="display:${this._visible ? 'flex' : 'none'}" class="admin-panel">
      <div class="admin-header">
        <span>🔧 管理面板</span>
        <button id="btnAdminClose" class="admin-close">×</button>
      </div>
      <div class="admin-body">
        <div class="admin-left">
          <div class="admin-section">
            <div class="admin-section-title">📋 NPC列表</div>
            <input type="text" id="adminNpcSearch" placeholder="搜索NPC..." class="admin-search"
                   oninput="AdminPanel._filterNpcList()">
            <div id="adminNpcList" class="admin-npc-list"></div>
          </div>
          <div class="admin-section">
            <div class="admin-section-title">🎮 游戏状态</div>
            <button onclick="AdminPanel._timeSkip()" class="admin-btn-sm">⏩ 时间+1小时</button>
            <button onclick="AdminPanel._timeSkip(24)" class="admin-btn-sm">⏩ 时间+1天</button>
            <select id="adminWeather" onchange="AdminPanel._setWeather(this.value)" class="admin-select">
              <option value="">☀️ 天气切换</option>
              <option value="sunny">☀️ 晴天</option>
              <option value="cloudy">☁️ 阴天</option>
              <option value="rainy">🌧️ 雨天</option>
              <option value="stormy">⛈️ 暴雨</option>
              <option value="snowy">🌨️ 雪天</option>
            </select>
          </div>
          <div class="admin-section">
            <div class="admin-section-title">
              🤖 模型管理
              <button onclick="AdminPanel._refreshModels()" class="admin-btn-sm" style="margin-left:auto;" title="刷新模型列表">🔄</button>
            </div>
            <div id="adminModelInfo" style="font-size:11px;color:#888;margin-bottom:8px;">
              点击刷新加载...
            </div>
            <div style="display:flex;gap:4px;margin-bottom:6px;">
              <select id="adminProvider" class="admin-select" style="flex:1;" onchange="AdminPanel._switchProvider(this.value)">
                <option value="">🔌 切换提供商...</option>
                <option value="deepseek">🤖 DeepSeek</option>
                <option value="lmstudio">🏠 LM Studio</option>
              </select>
            </div>
            <div style="display:flex;gap:4px;margin-bottom:6px;">
              <select id="adminModelTarget" class="admin-select" style="flex:1;">
                <option value="main">🎯 主模型 (玩家对话)</option>
                <option value="social">💬 社交模型 (NPC后台)</option>
              </select>
            </div>
            <div style="display:flex;gap:4px;">
              <select id="adminModelSelect" class="admin-select" style="flex:2;">
                <option value="">-- 选择模型 --</option>
              </select>
              <button onclick="AdminPanel._switchModel()" class="admin-btn-sm" style="flex:1;">✅ 切换</button>
            </div>
          </div>
          <div class="admin-section">
            <div class="admin-section-title">⚡ 快捷测试</div>
            <button onclick="AdminPanel._resetAll()" class="admin-btn-sm admin-btn-danger" style="width:100%;margin-bottom:4px">💣 重置所有记忆和对话</button>
            <button onclick="AdminPanel._trigger('npc_decide')" class="admin-btn-sm">🧠 强制NPC决策</button>
            <button onclick="AdminPanel._trigger('npc_social')" class="admin-btn-sm">💬 触发NPC社交</button>
            <button onclick="AdminPanel._trigger('npc_confess')" class="admin-btn-sm">💕 触发NPC告白</button>
            <button onclick="AdminPanel._trigger('npc_propose')" class="admin-btn-sm">💍 触发NPC求婚</button>
            <button onclick="AdminPanel._trigger('jealousy')" class="admin-btn-sm">😤 触发吃醋</button>
            <button onclick="AdminPanel._trigger('boundary_violation')" class="admin-btn-sm">🚫 触发越界</button>
            <button onclick="AdminPanel._resetCooldowns()" class="admin-btn-sm">🔄 重置冷却</button>
          </div>
          <div class="admin-section">
            <div class="admin-section-title">
              🖥️ 进程管理
              <button onclick="AdminPanel._refreshProcesses()" class="admin-btn-sm" style="margin-left:auto;" title="刷新进程状态">🔄</button>
            </div>
            <div id="adminProcessList" class="admin-process-list">
              <div class="admin-empty">点击刷新加载进程状态</div>
            </div>
          </div>
        </div>
        <div class="admin-right" id="adminDetail">
          <div class="admin-placeholder">← 选择一个NPC进行编辑</div>
        </div>
      </div>
    </div>`;

    const div = document.createElement('div');
    div.innerHTML = html;
    document.body.appendChild(div.firstElementChild);

    document.getElementById('btnAdminClose').addEventListener('click', () => this.toggle());
  },

  async _refreshAll() {
    await this._loadNpcList();
    await this._refreshProcesses();
  },

  async _loadNpcList() {
    try {
      const res = await fetch('/api/admin/npcs');
      const json = await res.json();
      this._allNpcs = json.data || [];
      this._filterNpcList();
    } catch (e) {
      console.error('Admin: failed to load NPCs', e);
    }
  },

  _filterNpcList() {
    const query = (document.getElementById('adminNpcSearch')?.value || '').toLowerCase();
    const list = document.getElementById('adminNpcList');
    if (!list) return;

    const npcs = (this._allNpcs || []).filter(n =>
      !query || n.name.toLowerCase().includes(query) || n.id.toLowerCase().includes(query)
    );

    list.innerHTML = npcs.map(n => {
      const moodMap = {happy:'😊', neutral:'😐', sad:'😢', angry:'😤', excited:'🤩', bored:'😴', fear:'😨', traumatized:'💔'};
      const mood = moodMap[n.current_mood] || '😐';
      const active = n.is_active ? '' : ' (停用)';
      const attrs = n.attributes || {};
      const sel = this._selectedNpcId === n.id ? 'admin-npc-item selected' : 'admin-npc-item';
      return `<div class="${sel}" onclick="AdminPanel._selectNpc('${n.id}')">
        <span>${mood}</span> <strong>${n.name}</strong>${active}
        <span style="font-size:9px;color:#999"> S${attrs.stamina||5} P${attrs.speed||5} T${attrs.strength||5}</span>
      </div>`;
    }).join('') || '<div class="admin-empty">无匹配NPC</div>';
  },

  async _selectNpc(npcId) {
    this._selectedNpcId = npcId;
    this._filterNpcList();

    try {
      const [npcRes, relsRes] = await Promise.all([
        fetch(`/api/admin/npcs/${npcId}`),
        fetch('/api/admin/relationships'),
      ]);
      const npc = (await npcRes.json()).data;
      const allRels = (await relsRes.json()).data || [];

      // Filter relationships for this NPC
      const npcRels = allRels.filter(r =>
        r.entity_a_id === npcId || r.entity_b_id === npcId
      );

      // Player relationship
      const playerRel = npcRels.find(r =>
        (r.entity_a_id === npcId && r.entity_b_id === 'player_001') ||
        (r.entity_b_id === npcId && r.entity_a_id === 'player_001')
      );

      const detail = document.getElementById('adminDetail');
      const attrs = npc.attributes || {};
      const presetTargetGender = npc.gender === 'male' ? 'female' : 'male';

      detail.innerHTML = `
        <div class="admin-card">
          <h3>${npc.name} <small>(${npcId})</small></h3>
          <div class="admin-card-section">
            <div class="admin-label">🏷️ 基础属性</div>
            <div class="admin-row">
              <span>体力</span>
              <input type="range" min="1" max="10" value="${attrs.stamina||5}"
                     oninput="AdminPanel._updateAttr('${npcId}','stamina',this.value)"
                     onchange="AdminPanel._saveAttr('${npcId}')">
              <span id="val-stamina-${npcId}">${attrs.stamina||5}</span>
            </div>
            <div class="admin-row">
              <span>速度</span>
              <input type="range" min="1" max="10" value="${attrs.speed||5}"
                     oninput="AdminPanel._updateAttr('${npcId}','speed',this.value)"
                     onchange="AdminPanel._saveAttr('${npcId}')">
              <span id="val-speed-${npcId}">${attrs.speed||5}</span>
            </div>
            <div class="admin-row">
              <span>力量</span>
              <input type="range" min="1" max="10" value="${attrs.strength||5}"
                     oninput="AdminPanel._updateAttr('${npcId}','strength',this.value)"
                     onchange="AdminPanel._saveAttr('${npcId}')">
              <span id="val-strength-${npcId}">${attrs.strength||5}</span>
            </div>
          </div>
          <div class="admin-card-section">
            <div class="admin-label">😊 心情</div>
            <select onchange="AdminPanel._saveMood('${npcId}', this.value)" class="admin-select">
              ${['neutral','happy','excited','sad','angry','bored','fear','traumatized'].map(m =>
                `<option value="${m}" ${npc.current_mood === m ? 'selected' : ''}>${m}</option>`
              ).join('')}
            </select>
          </div>
          <div class="admin-card-section">
            <div class="admin-label">🏠 场景位置</div>
            <select onchange="AdminPanel._saveLocation('${npcId}', this.value)" class="admin-select">
              <option value="">--移动--</option>
              <option value="scene_coffee_shop">☕ 咖啡店</option>
              <option value="scene_park">🌳 公园</option>
              <option value="scene_school">🏫 学校</option>
              <option value="scene_library">📚 图书馆</option>
              <option value="scene_market">🏪 超市</option>
            </select>
            <div style="font-size:11px;color:#999;margin-top:2px">当前: ${npc.current_scene_id || '无'}</div>
          </div>
          <div class="admin-card-section">
            <div class="admin-label">🏃 活动</div>
            <input type="text" value="${npc.current_activity || ''}" id="adminActivity-${npcId}"
                   class="admin-input" placeholder="输入活动描述">
            <button onclick="AdminPanel._saveActivity('${npcId}')" class="admin-btn-sm" style="margin-top:4px">保存活动</button>
          </div>
          <div class="admin-card-section">
            <div class="admin-label">🧠 性格标签</div>
            <input type="text" value="${(npc.personality||[]).join(', ')}" id="adminPersonality-${npcId}"
                   class="admin-input" placeholder="逗号分隔">
            <button onclick="AdminPanel._savePersonality('${npcId}')" class="admin-btn-sm" style="margin-top:4px">保存性格</button>
          </div>
          <div class="admin-card-section">
            <div class="admin-label">❤️ 与玩家的关系</div>
            <div class="admin-presets">
              <button onclick="AdminPanel._setRelPreset('${npcId}','stranger','${presetTargetGender}')" class="admin-btn-sm">陌生人</button>
              <button onclick="AdminPanel._setRelPreset('${npcId}','friend','${presetTargetGender}')" class="admin-btn-sm">朋友</button>
              <button onclick="AdminPanel._setRelPreset('${npcId}','lover','${presetTargetGender}')" class="admin-btn-sm">❤️恋人</button>
              <button onclick="AdminPanel._setRelPreset('${npcId}','spouse','${presetTargetGender}')" class="admin-btn-sm">💒配偶</button>
              <button onclick="AdminPanel._setRelPreset('${npcId}','enemy','${presetTargetGender}')" class="admin-btn-sm">💢仇敌</button>
            </div>
            ${playerRel ? `
            <div style="font-size:11px;margin-top:4px">
              好感: ${playerRel.favorability||0} | 熟悉: ${playerRel.familiarity||0} | 亲密: ${playerRel.intimacy_comfort||0}
              <br>类型: ${playerRel.relationship_type||'stranger'} | 吃醋: ${playerRel.jealousy_level||0}
            </div>` : '<div style="font-size:11px;color:#999">无现有关系</div>'}
          </div>
          <div class="admin-card-section">
            <div class="admin-label">🖼️ 头像</div>
            <div style="display:flex;align-items:center;gap:8px;margin-top:4px">
              ${npc.appearance?.avatar ? `<img src="${npc.appearance.avatar}" style="width:48px;height:48px;border-radius:50%;object-fit:cover">` : '<span style="color:#999">无头像</span>'}
              <span style="font-size:11px;color:#999">${npc.appearance?.avatar || '无头像'}</span>
            </div>
          </div>
        </div>`;
    } catch (e) {
      console.error('Admin: failed to load NPC detail', e);
    }
  },

  // ── Attribute editing (debounced) ──
  _attrPending: {},

  _updateAttr(npcId, attr, val) {
    const span = document.getElementById(`val-${attr}-${npcId}`);
    if (span) span.textContent = val;
    if (!this._attrPending[npcId]) this._attrPending[npcId] = {};
    this._attrPending[npcId][attr] = parseInt(val);
  },

  async _saveAttr(npcId) {
    const attrs = this._attrPending[npcId];
    if (!attrs) return;
    this._attrPending[npcId] = null;
    await fetch(`/api/admin/npcs/${npcId}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({attributes: attrs}),
    });
  },

  async _saveMood(npcId, mood) {
    await fetch(`/api/admin/npcs/${npcId}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({current_mood: mood}),
    });
  },

  async _saveLocation(npcId, sceneId) {
    if (!sceneId) return;
    await fetch(`/api/admin/npcs/${npcId}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({current_scene_id: sceneId}),
    });
  },

  async _saveActivity(npcId) {
    const val = document.getElementById(`adminActivity-${npcId}`)?.value || '';
    await fetch(`/api/admin/npcs/${npcId}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({current_activity: val}),
    });
  },

  async _savePersonality(npcId) {
    const val = document.getElementById(`adminPersonality-${npcId}`)?.value || '';
    const tags = val.split(',').map(s => s.trim()).filter(Boolean);
    await fetch(`/api/admin/npcs/${npcId}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({personality: tags}),
    });
  },

  async _setRelPreset(npcId, preset, targetGender) {
    await fetch('/api/admin/relationships', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        entity_a_id: npcId,
        entity_a_type: 'npc',
        entity_b_id: 'player_001',
        entity_b_type: 'player',
        preset: preset,
        target_gender: targetGender,
      }),
    });
    // Also set reverse
    await fetch('/api/admin/relationships', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        entity_a_id: 'player_001',
        entity_a_type: 'player',
        entity_b_id: npcId,
        entity_b_type: 'npc',
        preset: preset,
      }),
    });
    this._selectNpc(npcId);
  },

  // ── Game state ──
  async _timeSkip(hours = 1) {
    try {
      const res = await fetch('/api/admin/game-state');
      const state = (await res.json()).data;
      const gt = state.game_time || {day:1, hour:8, minute:0};
      let totalMinutes = gt.minute + hours * 60;
      gt.hour += Math.floor(totalMinutes / 60);
      gt.minute = totalMinutes % 60;
      while (gt.hour >= 24) { gt.hour -= 24; gt.day++; }
      await fetch('/api/admin/game-state', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({game_time: gt}),
      });
    } catch (e) {
      console.error('Admin: time skip failed', e);
    }
  },

  async _setWeather(type) {
    if (!type) return;
    await fetch('/api/admin/game-state', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({weather: type}),
    });
  },

  // ── Triggers ──

  // ── Model Management ──

  async _refreshModels() {
    const info = document.getElementById('adminModelInfo');
    const select = document.getElementById('adminModelSelect');
    if (!info || !select) return;

    try {
      const res = await fetch('/api/admin/models');
      const json = await res.json();
      const d = json.data || {};
      const cur = d.current || {};
      const available = d.available || [];

      const online = d.provider_online;
      const statusIcon = online === true ? '🟢' : online === false ? '🔴' : '⚪';
      const statusText = online === true ? '在线' : online === false ? '离线(显示兜底列表)' : '未知';
      info.innerHTML = `
        当前: 🎯 <strong>${cur.main_model || '?'}</strong> 
        &nbsp;|&nbsp; 💬 <strong>${cur.social_model || '?'}</strong>
        <br>${statusIcon} ${cur.provider || '?'} — ${statusText}
      `;

      // Set current provider in dropdown
      const providerSelect = document.getElementById('adminProvider');
      if (providerSelect && cur.provider) {
        providerSelect.value = cur.provider;
      }

      select.innerHTML = available.map(m => 
        `<option value="${m}" title="${m}">${m.length > 35 ? m.substring(0, 32) + '...' : m}</option>`
      ).join('');
    } catch (e) {
      console.error('Admin: failed to refresh models', e);
      info.innerHTML = '加载失败';
    }
  },

  async _switchModel() {
    const target = document.getElementById('adminModelTarget')?.value || 'main';
    const model = document.getElementById('adminModelSelect')?.value;
    if (!model) return;

    const info = document.getElementById('adminModelInfo');
    try {
      const res = await fetch('/api/admin/models/switch', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({target: target, model: model}),
      });
      const json = await res.json();
      if (json.status === 'ok') {
        if (info) info.innerHTML = `✅ 已切换! 正在生效...`;
        setTimeout(() => this._refreshModels(), 1500);
      } else {
        if (info) info.innerHTML = `❌ 切换失败`;
      }
    } catch (e) {
      console.error('Admin: switch model failed', e);
      if (info) info.innerHTML = '❌ 切换失败';
    }
  },

  async _switchProvider(provider) {
    if (!provider) return;
    const info = document.getElementById('adminModelInfo');
    try {
      const res = await fetch('/api/admin/provider/switch', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({provider: provider}),
      });
      const json = await res.json();
      if (json.status === 'ok') {
        if (info) info.innerHTML = `✅ 已切换到 ${provider}！正在生效...`;
        setTimeout(() => this._refreshModels(), 2000);
      } else {
        if (info) info.innerHTML = `❌ 切换失败`;
      }
    } catch (e) {
      console.error('Admin: switch provider failed', e);
      if (info) info.innerHTML = '❌ 切换失败';
    }
  },

  async _trigger(type) {
    await fetch('/api/admin/trigger', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({type: type, data: {}}),
    });
  },

  async _resetCooldowns() {
    if (!this._selectedNpcId) return;
    await fetch(`/api/admin/reset-cooldowns/${this._selectedNpcId}`, {method: 'POST'});
  },

  async _resetAll() {
    if (!confirm('确定要重置所有NPC的记忆和对话记录吗？\n\n这将删除所有对话历史、记忆，并将所有关系重置为陌生人。此操作不可撤销！')) return;
    try {
      const res = await fetch('/api/admin/reset-all', { method: 'POST' });
      const json = await res.json();
      if (json.status === 'ok') {
        const d = json.data;
        alert(`✅ 重置完成！\n\n删除对话: ${d.dialogues_deleted} 条\n删除记忆: ${d.memories_deleted} 条\n重置关系: ${d.relationships_reset} 条`);
        // Clear frontend state
        Store.clearDialogue();
        Store.set('selectedNpcId', null);
        Store.set('selectedNpcDetail', null);
        Dialogue.enableInput(false);
        App.showMain();
        this._refreshAll();
      }
    } catch (e) {
      console.error('Admin: reset all failed', e);
      alert('重置失败，请检查服务端日志');
    }
  },

  // ── Process management ──

  async _refreshProcesses() {
    const el = document.getElementById('adminProcessList');
    if (!el) return;
    try {
      const res = await fetch('/api/admin/processes');
      const json = await res.json();
      const data = json.data || {};
      const processes = data.processes || {};
      const names = Object.keys(processes);
      if (names.length === 0) {
        el.innerHTML = '<div class="admin-empty">无进程数据 (supervisor 未运行或 data/processes.json 不存在)</div>';
        return;
      }

      // Sort: system first, then gateways, then others
      const order = { system: 0, llm_gateway: 1, tts_gateway: 2, player: 3, api: 4 };
      names.sort((a, b) => {
        const oa = order[a] ?? (a.startsWith('npc_') ? 10 : 5);
        const ob = order[b] ?? (b.startsWith('npc_') ? 10 : 5);
        if (oa !== ob) return oa - ob;
        return a.localeCompare(b);
      });

      el.innerHTML = names.map(name => {
        const p = processes[name];
        const running = p.status === 'running';
        const statusIcon = running ? '🟢' : '🔴';
        const statusText = running ? '运行中' : `已停止 (exit: ${p.exit_code ?? '?'})`;
        const typeBadge = this._processTypeLabel(p.type);
        const desc = p.description || '';
        const pid = p.pid || '?';
        const isNpc = name.startsWith('npc_');
        const npcNum = isNpc ? name.replace('npc_', '').replace('photo_', '📷') : '';
        const displayName = isNpc ? npcNum : name;

        return `<div class="admin-process-card">
          <div class="admin-process-info">
            <div class="admin-process-name">
              ${statusIcon} <strong>${displayName}</strong>
              <span class="admin-process-type">${typeBadge}</span>
            </div>
            ${desc ? `<div class="admin-process-desc">${desc}</div>` : ''}
            <div class="admin-process-meta">PID: ${pid} · ${statusText}</div>
          </div>
          <div class="admin-process-actions">
            ${running ? `
              <button onclick="AdminPanel._processAction('${name}','restart')" class="admin-btn-sm" title="重启">🔄</button>
              <button onclick="AdminPanel._processAction('${name}','stop')" class="admin-btn-sm admin-btn-danger" title="停止">⏹️</button>
            ` : ''}
          </div>
        </div>`;
      }).join('');

      if (data.updated_at) {
        const ts = new Date(data.updated_at);
        el.innerHTML += `<div class="admin-process-updated">更新于: ${ts.toLocaleTimeString()}</div>`;
      }
    } catch (e) {
      console.error('Admin: failed to load processes', e);
      el.innerHTML = '<div class="admin-empty">加载失败</div>';
    }
  },

  _processTypeLabel(type) {
    const map = { system: '⚙️系统', gateway: '🌐网关', player: '👤玩家', npc: '🤖NPC' };
    return map[type] || type || '❓';
  },

  async _processAction(name, action) {
    if (!confirm(`确定要 ${action === 'restart' ? '重启' : '停止'} ${name}?`)) return;
    try {
      const res = await fetch(`/api/admin/processes/${name}/${action}`, { method: 'POST' });
      const json = await res.json();
      if (json.status === 'ok') {
        setTimeout(() => this._refreshProcesses(), 2000);
      }
    } catch (e) {
      console.error(`Admin: process ${action} failed`, e);
    }
  },
};
