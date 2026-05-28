/**
 * NPC card component for scene view grid.
 */
function renderNpcCard(npc) {
  const moodEmoji = {
    happy: '😊', excited: '🤩', neutral: '😐',
    sad: '😢', angry: '😠', bored: '🥱',
  };
  const selected = npc.id === Store.get('selectedNpcId') ? ' selected' : '';
  const inDialogue = npc.in_dialogue ? '<span class="npc-in-dialogue">对话中</span>' : '';

  // Auto action indicator
  const aa = npc.auto_action;
  const animClass = aa ? (ActionRenderer.ANIM_MAP[aa.animation] || '') : '';
  const catClass = aa ? `card-cat-${aa.category || 'solo'}` : '';
  const actionLabel = aa ? ActionRenderer.formatActionLabel(aa) : '';
  const actionIndicator = aa
    ? `<div class="npc-auto-action">${actionLabel}</div>`
    : '';

  // Avatar: use real photo if available, otherwise emoji fallback
  const avatarHtml = npc.avatar
    ? `<img class="npc-avatar-img" src="${npc.avatar}" alt="${npc.name}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">`
    + `<div class="npc-avatar ${npc.gender}" style="display:none;">${npc.gender === 'female' ? '👩' : npc.gender === 'male' ? '👨' : '🧑'}</div>`
    : `<div class="npc-avatar ${npc.gender}">${npc.gender === 'female' ? '👩' : npc.gender === 'male' ? '👨' : '🧑'}</div>`;

  return `
    <div class="npc-card${selected} ${animClass} ${catClass}" data-npc-id="${npc.id}" onclick="App.selectNpc('${npc.id}')">
      ${inDialogue}
      <span class="npc-mood">${moodEmoji[npc.mood] || '😐'}</span>
      ${avatarHtml}
      <div class="npc-name">${npc.name}</div>
      ${npc.career ? `<div class="npc-career">${npc.career}</div>` : `<div class="npc-role">${npc.role || '访客'}</div>`}
      <div class="npc-activity">${npc.activity || '闲逛中'}</div>
      ${actionIndicator}
    </div>`;
}
