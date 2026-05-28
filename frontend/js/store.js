/**
 * Reactive state store - simple pub/sub pattern.
 */
const Store = {
  _state: {
    playerId: 'player_001',
    connected: false,
    gameTime: { day: 1, hour: 8, minute: 0, season: 'spring', phase: 'morning', time_str: 'Day 1, 08:00' },
    weather: { type: 'sunny', emoji: '☀️', intensity: 'light' },
    scenes: [],
    currentSceneId: 'scene_coffee_shop',
    sceneDetail: null,
    npcs: {},
    selectedNpcId: null,
    selectedNpcDetail: null,
    dialogueMessages: [],
    isNpcTyping: false,
    activeEvents: [],
    idleSeconds: 600,
    socialCircleOpen: false,
    socialCircleTab: 'broadcasts',
    socialPosts: [],
    socialPostsLoading: false,
  },

  _listeners: {},

  get(path) {
    const keys = path.split('.');
    let v = this._state;
    for (const k of keys) v = v?.[k];
    return v;
  },

  set(path, value) {
    const keys = path.split('.');
    let obj = this._state;
    for (let i = 0; i < keys.length - 1; i++) {
      if (!(keys[i] in obj)) obj[keys[i]] = {};
      obj = obj[keys[i]];
    }
    const old = obj[keys[keys.length - 1]];
    obj[keys[keys.length - 1]] = value;

    // Notify listeners on this path and parent paths
    for (const [pattern, cbs] of Object.entries(this._listeners)) {
      if (path.startsWith(pattern) || pattern.startsWith(path.split('.')[0])) {
        cbs.forEach(fn => fn(value, old));
      }
    }
  },

  on(path, fn) {
    if (!this._listeners[path]) this._listeners[path] = [];
    this._listeners[path].push(fn);
    return () => {
      this._listeners[path] = this._listeners[path].filter(f => f !== fn);
    };
  },

  // Convenience mutators
  setNpcState(npcId, data) {
    const npcs = { ...this._state.npcs };
    npcs[npcId] = { ...(npcs[npcId] || {}), ...data };
    this.set('npcs', npcs);
  },

  addDialogue(msg) {
    const msgs = [...this._state.dialogueMessages, msg];
    this.set('dialogueMessages', msgs);
  },

  clearDialogue() {
    this.set('dialogueMessages', []);
  },

  addSocialEvent(data) {
    const events = [...(this._state.socialEvents || [])];
    events.push({ ...data, _ts: Date.now() });
    if (events.length > 50) events.shift();
    this.set('socialEvents', events);

    // Create popup bubble for scene view
    const npcId = data.npc_id;
    if (npcId) {
      const bubbles = { ...(this._state.socialBubbles || {}) };
      const content = data.content || data.action_name || '';
      const bubble = {
        id: data.interaction_id || Date.now().toString(),
        npcId: npcId,
        npcName: data.npc_name || '',
        content: content,
        phase: data.phase || '',
        actionName: data.action_name || '',
        targetName: data.target_name || '',
        icon: data.icon || '',
        animation: data.animation || 'none',
        category: data.category || 'solo',
        durationTicks: parseInt(data.duration_ticks) || 3,
        _ts: Date.now(),
      };
      bubbles[npcId] = bubble;
      this.set('socialBubbles', bubbles);
    }
  },

  clearSocialBubble(npcId) {
    const bubbles = { ...(this._state.socialBubbles || {}) };
    delete bubbles[npcId];
    this.set('socialBubbles', bubbles);
  },
};
