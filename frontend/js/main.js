/**
 * Application bootstrap. Initializes all panels and connects to server.
 */
const App = {
  _currentView: 'main',  // 'main' | 'dialogue' | 'social' | 'character' | 'settings'

  async init() {
    // Connect WebSocket
    const playerId = Store.get('playerId');
    WSClient.connect(playerId);

    // Initialize all panels
    TopBar.init();
    await Sidebar.init();   // Now powers sceneBar + characterView
    SceneView.init();
    Dialogue.init();
    GALDialogue.init();
    SocialCircle.init();
    AdminPanel.init();
    PlayerSettings.init();

    // Fetch player's actual location (may differ from default)
    try {
      const loc = await API.getPlayerLocation(playerId);
      if (loc && loc.scene_id) {
        Store.set('currentSceneId', loc.scene_id);
      }
    } catch (e) {
      console.warn('Failed to fetch player location, using default:', e);
    }

    // Select initial scene (via Sidebar which now populates sceneBar)
    await Sidebar.selectScene(Store.get('currentSceneId'));

    // Fetch player data (for portrait, name, etc.)
    try {
      const player = await API.getPlayer(playerId);
      if (player) Store.set('playerData', player);
    } catch (e) {
      console.warn('Failed to fetch player data:', e);
    }

    // Initial data fetch
    try {
      const time = await API.getTime();
      if (time) Store.set('gameTime', time);
      const weather = await API.getWeather();
      if (weather) Store.set('weather', weather);
    } catch (e) {
      console.error('Failed to fetch initial state:', e);
    }

    console.log('🏘️ 城市小镇 ready!');
    console.log('💡 Click on an NPC in the scene view to start a conversation.');
  },

  // ── View Switching ──────────────────────────────

  showMain() {
    // Hide sub-views but keep player settings if user is editing
    document.getElementById('galDialogueOverlay').style.display = 'none';
    document.getElementById('socialView').style.display = 'none';
    document.getElementById('characterView').style.display = 'none';
    // Only hide player settings if it's not currently open (user might be editing)
    var psOverlay = document.getElementById('playerSettingsOverlay');
    if (psOverlay && psOverlay.style.display !== 'flex') {
      psOverlay.style.display = 'none';
    }
    // Show main
    document.getElementById('mainView').style.display = 'flex';
    this._currentView = 'main';
    Store.set('socialCircleOpen', false);
  },

  showSocial() {
    document.getElementById('mainView').style.display = 'none';
    document.getElementById('socialView').style.display = 'flex';
    this._currentView = 'social';
    Store.set('socialCircleOpen', true);
  },

  showCharacter(npcId) {
    document.getElementById('mainView').style.display = 'none';
    document.getElementById('characterView').style.display = 'flex';
    this._currentView = 'character';
    if (npcId) Sidebar.showNpcDetail(npcId);
  },

  // ── NPC Selection ───────────────────────────────

  selectNpc(npcId) {
    const current = Store.get('selectedNpcId');
    if (current === npcId) {
      // Deselect
      Store.set('selectedNpcId', null);
      GALDialogue.hide();
      this.showMain();
      SceneView.render(Store.get('sceneDetail'));
    } else {
      // Select — show GAL dialogue overlay
      Store.set('selectedNpcId', npcId);
      GALDialogue.show(npcId);
      SceneView.render(Store.get('sceneDetail'));
    }
  },

  async resetAll() {
    if (!confirm('确定要重置所有NPC的记忆和对话记录吗？\n\n这将删除所有对话历史、记忆，并将所有关系重置为陌生人。\n此操作不可撤销！')) return;
    try {
      const res = await fetch('/api/admin/reset-all', { method: 'POST' });
      const json = await res.json();
      if (json.status === 'ok') {
        const d = json.data;
        alert(`✅ 重置完成！\n删除对话: ${d.dialogues_deleted} 条\n删除记忆: ${d.memories_deleted} 条\n重置关系: ${d.relationships_reset} 条`);
        Store.clearDialogue();
        window._lastNpcMsgByNpc = {};
        Store.set('selectedNpcId', null);
        Store.set('selectedNpcDetail', null);
        Dialogue.enableInput(false);
        GALDialogue.hide();
        Sidebar.showNpcDetail(null);
        this.showMain();
      }
    } catch (e) {
      console.error('Reset all failed:', e);
      alert('重置失败，请检查服务端日志');
    }
  },
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
