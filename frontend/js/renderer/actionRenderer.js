/**
 * Abstract action rendering layer.
 * Maps AnimType → CSS classes. Forward-compatible with future 2D sprite engine:
 * swap the mapping table without touching any consumer code.
 */
const ActionRenderer = {
  /** AnimType → CSS animation class */
  ANIM_MAP: {
    none: '',
    pulse: 'css-pulse',
    bounce: 'css-bounce',
    swing: 'css-swing',
    shake: 'css-shake',
    float: 'css-float',
    spin: 'css-spin',
    fade: 'css-fade',
  },

  /** Category → bubble color class */
  CATEGORY_BUBBLE: {
    solo: 'auto-bubble-solo',
    friendly: 'auto-bubble-friendly',
    intimate: 'auto-bubble-intimate',
    couple: 'auto-bubble-couple',
    negative: 'auto-bubble-negative',
    force: 'auto-bubble-force',
    agility: 'auto-bubble-agility',
  },

  /**
   * Apply an animation class to an NPC card element.
   * Removes any previously applied css-* animation class first.
   */
  applyCardAnimation(cardEl, animation, category) {
    if (!cardEl) return;
    // Remove old animation classes
    cardEl.classList.forEach(cls => {
      if (cls.startsWith('css-')) cardEl.classList.remove(cls);
    });
    // Remove old category modifiers
    cardEl.classList.forEach(cls => {
      if (cls.startsWith('card-cat-')) cardEl.classList.remove(cls);
    });

    const animClass = this.ANIM_MAP[animation];
    if (animClass) cardEl.classList.add(animClass);
    if (category) cardEl.classList.add(`card-cat-${category}`);
  },

  /** Remove all action animation classes from a card. */
  clearCardAnimation(cardEl) {
    if (!cardEl) return;
    cardEl.classList.forEach(cls => {
      if (cls.startsWith('css-') || cls.startsWith('card-cat-')) cardEl.classList.remove(cls);
    });
  },

  /** Get the bubble CSS class for an auto_action event. */
  getBubbleClass(category) {
    return this.CATEGORY_BUBBLE[category] || 'auto-bubble-solo';
  },

  /** Build a display string for the action on an NPC card. */
  formatActionLabel(actionData) {
    if (!actionData) return '';
    const icon = actionData.icon || '';
    const text = actionData.display_text || actionData.action_name || '';
    return `${icon} ${text}`;
  },
};
