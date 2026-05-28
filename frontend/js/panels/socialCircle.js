/**
 * Panel 5: Social Circle floating panel - broadcasts, posts, NPC detail.
 * Uses event delegation for all dynamically generated content.
 */
const SocialCircle = {
  _postsTimer: null,
  _detailNpcId: null,

  init() {
    const panel = document.getElementById('socialView');
    if (!panel) return;

    this._initTabs();
    this._initContentDelegation();

    // Topbar toggle button
    const btn = document.getElementById('btnSocialCircle');
    if (btn) btn.addEventListener('click', () => this.toggle());

    // Header action buttons
    const btnFilter = document.getElementById('btnSocialFilterToggle');
    const btnClose = document.getElementById('btnSocialClose');
    if (btnFilter) btnFilter.addEventListener('click', () => {
      const filters = document.getElementById('socialFilters');
      if (filters) filters.style.display = filters.style.display === 'none' ? 'flex' : 'none';
    });
    if (btnClose) btnClose.addEventListener('click', (e) => { e.stopPropagation(); this.hide(); });

    // Listen for social events (real-time broadcasts)
    Store.on('socialEvents', () => {
      if (Store.get('socialCircleOpen') && Store.get('socialCircleTab') === 'broadcasts') {
        this._renderBroadcasts();
      }
    });

    // Listen for NPC state changes to refresh detail view
    Store.on('npcs', () => {
      if (Store.get('socialCircleOpen') && Store.get('socialCircleTab') === 'npc_detail' && this._detailNpcId) {
        this._renderNpcDetail();
      }
    });

    // Listen for state changes (only update DOM, navigation is handled by App)
    Store.on('socialCircleOpen', (open) => {
      const panel = document.getElementById('socialView');
      if (open) {
        if (panel) panel.style.display = 'flex';
        this._onOpen();
        if (btn) btn.classList.add('active');
      } else {
        if (panel) panel.style.display = 'none';
        this._stopPolling();
        if (btn) btn.classList.remove('active');
      }
    });

    Store.on('socialCircleTab', () => this._onTabChange());
  },

  // ── Event Delegation ─────────────────────────────

  _initContentDelegation() {
    const content = document.getElementById('socialContent');
    if (!content) return;

    content.addEventListener('click', (e) => {
      // Author name click → open NPC detail
      const author = e.target.closest('.social-card-author');
      if (author) {
        const npcId = author.dataset.npcId;
        if (npcId) this.openTab('npc_detail', npcId);
        return;
      }

      // Like button
      const likeBtn = e.target.closest('.btn-like-post');
      if (likeBtn) {
        this._likePost(likeBtn.dataset.postId, likeBtn);
        return;
      }

      // Toggle comments button
      const commentBtn = e.target.closest('.btn-toggle-comments');
      if (commentBtn) {
        this._toggleComments(commentBtn.dataset.postId);
        return;
      }

      // Submit comment button
      const submitBtn = e.target.closest('.btn-comment-submit');
      if (submitBtn) {
        this._submitComment(submitBtn.dataset.postId);
        return;
      }

      // Back to NPC select button
      const backBtn = e.target.closest('[data-action="back-to-npc-select"]');
      if (backBtn) {
        this._detailNpcId = null;
        this._renderNpcDetail();
        return;
      }

      // Relationship NPC name click → switch to that NPC's detail
      const relName = e.target.closest('.social-npc-rel-name');
      if (relName) {
        const npcId = relName.dataset.npcId;
        if (npcId) this._selectNpc(npcId);
        return;
      }
    });

    // Select change delegation (NPC select + quick-switch)
    content.addEventListener('change', (e) => {
      const select = e.target.closest('#socialNpcSelect');
      if (select && select.value) {
        this._selectNpc(select.value);
        return;
      }
      const quickSwitch = e.target.closest('.social-npc-quick-switch');
      if (quickSwitch && quickSwitch.value) {
        this._selectNpc(quickSwitch.value);
      }
    });
  },

  // ── Visibility ─────────────────────────────────

  toggle() {
    const open = Store.get('socialCircleOpen');
    if (open) {
      App.showMain();
    } else {
      App.showSocial();
    }
  },

  show() {
    App.showSocial();
  },

  hide() {
    App.showMain();
  },

  _onOpen() {
    const tab = Store.get('socialCircleTab') || 'broadcasts';
    this._switchTab(tab);
  },

  openTab(tab, npcId) {
    Store.set('socialCircleTab', tab);
    if (npcId) this._detailNpcId = npcId;
    this.show();
  },

  // ── Tabs ───────────────────────────────────────

  _initTabs() {
    const tabs = document.getElementById('socialTabs');
    if (!tabs) return;
    tabs.addEventListener('click', (e) => {
      const tabBtn = e.target.closest('.social-tab');
      if (!tabBtn) return;
      Store.set('socialCircleTab', tabBtn.dataset.tab);
    });
  },

  _onTabChange() {
    this._switchTab(Store.get('socialCircleTab'));
  },

  _switchTab(tab) {
    document.querySelectorAll('.social-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    const filters = document.getElementById('socialFilters');
    if (filters) filters.style.display = (tab === 'posts') ? 'flex' : 'none';

    if (tab === 'posts') this._initFilters();

    this._stopPolling();
    switch (tab) {
      case 'broadcasts': this._renderBroadcasts(); break;
      case 'posts': this._loadPosts(); this._startPolling(); break;
      case 'npc_detail': this._renderNpcDetail(); break;
    }
  },

  // ── Filters ────────────────────────────────────

  async _initFilters() {
    const npcSelect = document.getElementById('socialFilterNpc');
    const typeSelect = document.getElementById('socialFilterType');

    if (npcSelect && npcSelect.options.length <= 1) {
      npcSelect.innerHTML = '<option value="">全部NPC</option>';
      let npcEntries = [];
      try {
        const list = await API.getNpcs();
        if (list && list.length > 0) {
          npcEntries = list.map(n => [n.id, n]);
        }
      } catch (e) { console.error('Failed to load NPC list:', e); }
      if (npcEntries.length === 0) {
        const npcs = Store.get('npcs') || {};
        npcEntries = Object.entries(npcs);
      }
      npcEntries.forEach(([id, data]) => {
        npcSelect.innerHTML += `<option value="${id}">${data.name || id}</option>`;
      });
    }

    if (typeSelect && typeSelect.options.length <= 1) {
      typeSelect.innerHTML = `
        <option value="">全部类型</option>
        <option value="general">日常</option>
        <option value="confession">告白</option>
        <option value="life_event">生活事件</option>`;
    }

    if (npcSelect) npcSelect.onchange = () => this._loadPosts();
    if (typeSelect) typeSelect.onchange = () => this._loadPosts();
  },

  // ── Tab: Broadcasts ────────────────────────────

  _renderBroadcasts() {
    const content = document.getElementById('socialContent');
    if (!content) return;

    const events = Store.get('socialEvents') || [];
    if (events.length === 0) {
      content.innerHTML = '<div class="empty-hint">暂无广播，等待NPC互动...</div>';
      return;
    }

    const reversed = [...events].reverse();
    content.innerHTML = reversed.map(e => this._renderBroadcastCard(e)).join('');
  },

  _renderBroadcastCard(e) {
    const npcName = this._escapeHtml(e.npc_name || e.npc_id || '?');
    const npcId = e.npc_id || '';
    const targetName = this._escapeHtml(e.target_name || '');
    const text = this._escapeHtml(e.content || e.action_name || '');
    const phase = e.phase || '';
    const icon = e.icon || '';

    // Auto_action events get special formatting
    const isAutoAction = phase === 'auto_action';
    const catClass = isAutoAction ? `auto-cat-${e.category || 'solo'}` : '';
    const phaseLabel = isAutoAction ? this._escapeHtml(e.action_name || 'auto') : phase;
    const phaseTag = phase
      ? `<span class="social-card-tag ${phase} ${catClass}">${icon} ${phaseLabel}</span>`
      : '';

    return `
      <div class="social-card${isAutoAction ? ' social-card-auto' : ''}">
        <div class="social-card-header">
          <div class="social-card-avatar">👤</div>
          <span class="social-card-author" data-npc-id="${npcId}">${npcName}</span>
          ${targetName ? `<span style="font-size:11px;color:var(--text-muted);">→ ${targetName}</span>` : ''}
          ${phaseTag}
        </div>
        <div class="social-card-body">${icon} ${text}</div>
      </div>`;
  },

  // ── Tab: Posts ─────────────────────────────────

  _startPolling() {
    this._stopPolling();
    this._postsTimer = setInterval(() => this._loadPosts(), 30000);
  },

  _stopPolling() {
    if (this._postsTimer) { clearInterval(this._postsTimer); this._postsTimer = null; }
  },

  async _loadPosts() {
    const content = document.getElementById('socialContent');
    if (!content) return;

    Store.set('socialPostsLoading', true);
    content.innerHTML = '<div class="empty-hint">加载中...</div>';

    try {
      const authorId = document.getElementById('socialFilterNpc')?.value || '';
      const postType = document.getElementById('socialFilterType')?.value || '';
      const posts = await API.getSocialFeed({ authorId, postType, limit: 30 });
      Store.set('socialPosts', posts);
      this._renderPosts(posts);
    } catch (e) {
      console.error('Failed to load social feed:', e);
      content.innerHTML = '<div class="empty-hint">加载失败，请重试</div>';
    } finally {
      Store.set('socialPostsLoading', false);
    }
  },

  _renderPosts(posts) {
    const content = document.getElementById('socialContent');
    if (!content) return;

    if (!posts || posts.length === 0) {
      content.innerHTML = '<div class="empty-hint">暂无帖子</div>';
      return;
    }

    content.innerHTML = posts.map(p => this._renderPostCard(p)).join('');
  },

  _renderPostCard(p) {
    const authorName = this._escapeHtml(p.author_name || p.author_id || '?');
    const authorId = p.author_id || '';
    const text = this._escapeHtml(p.content || '');
    const mood = p.mood ? `<span class="social-card-mood">${this._escapeHtml(p.mood)}</span>` : '';
    const gameTime = this._escapeHtml(p.game_time || '');
    const likeCount = p.like_count || 0;
    const commentCount = p.comment_count || 0;

    return `
      <div class="social-card" data-post-id="${p.id}">
        <div class="social-card-header">
          <div class="social-card-avatar">👤</div>
          <span class="social-card-author" data-npc-id="${authorId}">${authorName}</span>
          ${mood}
          <span class="social-card-time">${gameTime}</span>
        </div>
        <div class="social-card-body">${text}</div>
        <div class="social-card-footer">
          <button class="btn-social-action btn-like-post" data-post-id="${p.id}">❤️ ${likeCount}</button>
          <button class="btn-social-action btn-toggle-comments" data-post-id="${p.id}">💬 ${commentCount} 评论</button>
        </div>
        <div class="social-comments" id="comments-${p.id}" style="display:none;"></div>
      </div>`;
  },

  // ── Like ───────────────────────────────────────

  async _likePost(postId, btn) {
    const playerId = Store.get('playerId') || 'player_001';
    try {
      const result = await API.likeSocialPost(postId, playerId);
      if (result.liked) {
        btn.classList.add('liked');
        const match = btn.textContent.match(/\d+/);
        if (match) btn.textContent = `❤️ ${parseInt(match[0]) + 1}`;
      }
    } catch (e) { console.error('Like failed:', e); }
  },

  // ── Comments ───────────────────────────────────

  async _toggleComments(postId) {
    const el = document.getElementById('comments-' + postId);
    if (!el) return;

    if (el.style.display === 'none' || !el.style.display) {
      el.style.display = 'block';
      await this._loadComments(postId, el);
      const inputRow = document.createElement('div');
      inputRow.className = 'social-comment-input-row';
      inputRow.innerHTML = `
        <input class="social-comment-input" id="commentInput-${postId}" placeholder="写评论...">
        <button class="btn-comment-submit" data-post-id="${postId}">发送</button>`;
      el.appendChild(inputRow);
    } else {
      el.style.display = 'none';
      el.innerHTML = '';
    }
  },

  async _loadComments(postId, el) {
    try {
      const comments = await API.getSocialPostComments(postId);
      if (!comments || comments.length === 0) {
        el.innerHTML = '<div style="font-size:11px;color:var(--text-muted);">暂无评论</div>';
        return;
      }
      el.innerHTML = comments.map(c => `
        <div class="social-comment">
          <span class="social-comment-author">${this._escapeHtml(c.author_name || '?')}:</span>
          ${this._escapeHtml(c.content || '')}
        </div>`).join('');
    } catch (e) {
      console.error('Failed to load comments:', e);
      el.innerHTML = '<div style="font-size:11px;color:var(--text-muted);">加载失败</div>';
    }
  },

  async _submitComment(postId) {
    const input = document.getElementById('commentInput-' + postId);
    if (!input) return;
    const content = input.value.trim();
    if (!content) return;

    const playerId = Store.get('playerId') || 'player_001';
    try {
      await API.commentSocialPost(postId, playerId, content);
      input.value = '';
      const el = document.getElementById('comments-' + postId);
      if (el) {
        await this._loadComments(postId, el);
        const inputRow = document.createElement('div');
        inputRow.className = 'social-comment-input-row';
        inputRow.innerHTML = `
          <input class="social-comment-input" id="commentInput-${postId}" placeholder="写评论...">
          <button class="btn-comment-submit" data-post-id="${postId}">发送</button>`;
        el.appendChild(inputRow);
      }
    } catch (e) { console.error('Comment failed:', e); }
  },

  // ── Tab: NPC Detail ────────────────────────────

  async _renderNpcDetail() {
    const content = document.getElementById('socialContent');
    if (!content) return;

    if (!this._detailNpcId) {
      content.innerHTML = `
        <div class="social-npc-detail">
          <div class="detail-label">选择一个NPC查看详情</div>
          <select class="social-npc-select" id="socialNpcSelect">
            <option value="">-- 选择NPC --</option>
          </select>
          <div id="socialNpcDetailContent"></div>
        </div>`;
      this._populateNpcSelect();
      return;
    }

    content.innerHTML = '<div class="empty-hint">加载中...</div>';
    try {
      const playerId = Store.get('playerId') || 'player_001';
      const [npc, rel, rels] = await Promise.all([
        API.getNpc(this._detailNpcId),
        API.getNpcRelationship(this._detailNpcId, playerId),
        API.getNpcRelationships(this._detailNpcId).catch(() => ({ outgoing: [], incoming: [] })),
      ]);
      content.innerHTML = this._renderNpcDetailCard(npc, rel, rels);
      this._populateQuickSwitch(npc.id);
    } catch (e) {
      console.error('Failed to load NPC detail:', e);
      content.innerHTML = '<div class="empty-hint">加载NPC信息失败</div>';
    }
  },

  async _populateNpcSelect() {
    const select = document.getElementById('socialNpcSelect');
    if (!select) return;

    let npcEntries = [];
    try {
      const list = await API.getNpcs();
      if (list && list.length > 0) {
        npcEntries = list.map(n => [n.id, n]);
      }
    } catch (e) { console.error('Failed to load NPC list:', e); }

    // Fallback to Store
    if (npcEntries.length === 0) {
      const npcs = Store.get('npcs') || {};
      npcEntries = Object.entries(npcs);
    }

    select.innerHTML = '<option value="">-- 选择NPC --</option>';
    npcEntries.forEach(([id, data]) => {
      select.innerHTML += `<option value="${id}">${data.name || id}</option>`;
    });
  },

  async _populateQuickSwitch(currentNpcId) {
    const select = document.querySelector('.social-npc-quick-switch');
    if (!select) return;

    let npcEntries = [];
    try {
      const list = await API.getNpcs();
      if (list && list.length > 0) {
        npcEntries = list.map(n => [n.id, n]);
      }
    } catch (e) { console.error('Failed to load NPC list:', e); }

    // Fallback to Store
    if (npcEntries.length === 0) {
      const npcs = Store.get('npcs') || {};
      npcEntries = Object.entries(npcs);
    }

    select.innerHTML = '<option value="">切换NPC...</option>';
    npcEntries.forEach(([id, data]) => {
      const sel = id === currentNpcId ? ' selected' : '';
      select.innerHTML += `<option value="${id}"${sel}>${data.name || id}</option>`;
    });
  },

  _selectNpc(npcId) {
    if (!npcId) return;
    this._detailNpcId = npcId;
    this._renderNpcDetail();
  },

  _renderNpcDetailCard(npc, rel, rels) {
    const personality = Array.isArray(npc.personality) ? npc.personality : [];
    const appearance = npc.appearance || {};
    const goals = npc.goals || [];
    const genderEmoji = npc.gender === 'male' ? '👦' : npc.gender === 'female' ? '👧' : '🧑';

    let relHtml = '';
    if (rel) {
      const favPct = Math.max(0, Math.min(100, ((rel.favorability || 0) + 100) / 2));
      const famPct = Math.max(0, Math.min(100, rel.familiarity || 0));
      relHtml = `
        <div class="detail-section">
          <div class="detail-label">与你的关系</div>
          <div class="detail-value">
            ${rel.relationship_type ? `关系: ${rel.relationship_type}<br>` : ''}
            <div style="margin:4px 0;">
              <span style="font-size:11px;">❤️ 好感 ${rel.favorability || 0}</span>
              <div class="rel-progress"><div class="rel-fill fav-fill" style="width:${favPct}%"></div></div>
            </div>
            <div style="margin:4px 0;">
              <span style="font-size:11px;">👋 熟悉 ${rel.familiarity || 0}</span>
              <div class="rel-progress"><div class="rel-fill fam-fill" style="width:${famPct}%"></div></div>
            </div>
          </div>
        </div>`;
    }

    let npcRelsHtml = '';
    const outgoing = rels.outgoing || [];
    if (outgoing.length > 0) {
      npcRelsHtml += '<div class="detail-section"><div class="detail-label">NPC关系网络</div>';
      outgoing.forEach(r => {
        const favColor = r.favorability > 50 ? 'var(--mood-happy)' :
                         r.favorability < -20 ? 'var(--mood-angry)' : 'var(--text-secondary)';
        const targetId = r.entity_b_id || r.target_id || '';
        npcRelsHtml += `
          <div class="social-npc-rel-item">
            <span class="social-npc-rel-name" data-npc-id="${targetId}" style="cursor:pointer;text-decoration:underline;" title="点击查看NPC详情">${this._escapeHtml(r.target_name || r.entity_b_id)}</span>
            <span class="social-npc-rel-type">${this._escapeHtml(r.relationship_type || 'stranger')}</span>
            <span class="social-npc-rel-fav" style="color:${favColor}">好感: ${r.favorability || 0}</span>
          </div>`;
      });
      npcRelsHtml += '</div>';
    }

    return `
      <div class="social-npc-detail">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
          <button class="btn-back-npc-select" data-action="back-to-npc-select" title="返回NPC选择">← 返回</button>
          <select class="social-npc-select social-npc-quick-switch">
            <option value="">切换NPC...</option>
          </select>
        </div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
          <div class="social-card-avatar" style="width:40px;height:40px;font-size:20px;">${genderEmoji}</div>
          <div>
            <div class="detail-name">${this._escapeHtml(npc.name)}</div>
            <div style="font-size:11px;color:var(--text-muted);">
              ${npc.gender === 'male' ? '男' : npc.gender === 'female' ? '女' : '其他'} ·
              出生: ${npc.birth_date || '?'} · 音色: ${npc.voice_type || '?'}
            </div>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">性格</div>
          <div class="personality-tags">
            ${personality.map(p => `<span class="personality-tag">${this._escapeHtml(p)}</span>`).join('')}
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">外貌</div>
          <div class="detail-value">${Object.entries(appearance).map(([k,v]) => `${k}: ${v}`).join(', ') || '暂无信息'}</div>
        </div>

        ${relHtml}
        ${npcRelsHtml}

        ${goals.length ? `
        <div class="detail-section">
          <div class="detail-label">当前目标</div>
          <div class="detail-value">
            ${goals.map(g => `• [${this._escapeHtml(g.goal_type || '')}] ${this._escapeHtml(g.description || '')}`).join('<br>')}
          </div>
        </div>` : ''}

        <div class="detail-section">
          <div class="detail-label">所在场景</div>
          <div class="detail-value">${this._escapeHtml(npc.scene_name || '未知')} (${this._escapeHtml(npc.current_activity || '空闲中')})</div>
        </div>

        ${this._renderNpcCurrentAction(this._detailNpcId)}
      </div>`;
  },

  // ── Helpers ────────────────────────────────────

  _renderNpcCurrentAction(npcId) {
    if (!npcId) return '';
    const npcState = Store.get('npcs')?.[npcId];
    const aa = npcState?.auto_action;
    if (!aa) return '';
    return `
      <div class="detail-section">
        <div class="detail-label">当前状态</div>
        <div class="detail-value" style="color: var(--mood-happy);">${this._escapeHtml(aa.icon || '')} ${this._escapeHtml(aa.display_text || aa.action_name || '')}</div>
      </div>`;
  },

  _escapeHtml(str) {
    if (!str) return '';
    const s = String(str);
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
  },
};
