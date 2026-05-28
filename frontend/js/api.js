/**
 * REST API client helpers.
 */
const API = {
  BASE: '/api/v1',

  async _fetch(url, opts = {}) {
    const res = await fetch(this.BASE + url, {
      headers: { 'Content-Type': 'application/json', ...opts.headers },
      ...opts,
    });
    if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
    const json = await res.json();
    if (json.status === 'error') throw new Error(json.error);
    return json.data;
  },

  // Scenes
  async getScenes() {
    return this._fetch('/scenes');
  },

  async getScene(sceneId) {
    return this._fetch(`/scene/${sceneId}?player_id=${Store.get('playerId')}`);
  },

  async getSceneNpcs(sceneId) {
    return this._fetch(`/scene/${sceneId}/npcs`);
  },

  // NPCs
  async getNpcs() {
    return this._fetch('/npcs');
  },

  async getNpc(npcId) {
    return this._fetch(`/npc/${npcId}`);
  },

  async getNpcRelationship(npcId, playerId) {
    return this._fetch(`/npc/${npcId}/relationship/${playerId}`);
  },

  async getNpcRelationships(npcId) {
    return this._fetch(`/npc/${npcId}/relationships`);
  },

  async updateNpcRelationship(npcId, playerId, data) {
    return this._fetch(`/npc/${npcId}/relationship/${playerId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  // Player
  async getPlayer(playerId) {
    return this._fetch(`/player/${playerId}`);
  },

  async getPlayerLocation(playerId) {
    return this._fetch(`/player/${playerId}/location`);
  },

  async updatePlayer(playerId, data) {
    return this._fetch(`/player/${playerId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async getPlayerRelationships(playerId) {
    return this._fetch(`/player/${playerId}/relationships`);
  },

  // System
  async getTime() {
    return this._fetch('/system/time');
  },

  async getWeather() {
    return this._fetch('/system/weather');
  },

  async getEvents(sceneId = '') {
    const q = sceneId ? `?scene_id=${sceneId}` : '';
    return this._fetch(`/system/events${q}`);
  },

  // Dialogue
  async sendDialogue(playerId, npcId, content) {
    return this._fetch('/dialogue', {
      method: 'POST',
      body: JSON.stringify({ player_id: playerId, npc_id: npcId, content }),
    });
  },

  async getDialogueHistory(playerId, npcId, limit = 50) {
    return this._fetch(`/dialogue/history/${playerId}/${npcId}?limit=${limit}`);
  },

  // Social feed
  async getSocialFeed({ postType = '', authorId = '', limit = 20, offset = 0 } = {}) {
    const params = new URLSearchParams();
    if (postType) params.set('post_type', postType);
    if (authorId) params.set('author_id', authorId);
    params.set('limit', limit);
    params.set('offset', offset);
    return this._fetch(`/social/feed?${params}`);
  },

  async getSocialPost(postId) {
    return this._fetch(`/social/post/${postId}`);
  },

  async getSocialPostComments(postId, limit = 10) {
    return this._fetch(`/social/post/${postId}/comments?limit=${limit}`);
  },

  async likeSocialPost(postId, playerId) {
    return this._fetch(`/social/post/${postId}/like`, {
      method: 'POST',
      body: JSON.stringify({ player_id: playerId }),
    });
  },

  async commentSocialPost(postId, playerId, content) {
    return this._fetch(`/social/post/${postId}/comment`, {
      method: 'POST',
      body: JSON.stringify({ player_id: playerId, content }),
    });
  },
};
