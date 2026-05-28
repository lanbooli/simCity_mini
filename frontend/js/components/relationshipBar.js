/**
 * Relationship bar component - renders favorability/familiarity progress bars.
 */
function renderRelationshipBars(favorability, familiarity) {
  const favPct = ((favorability + 100) / 200 * 100).toFixed(0);
  const famPct = Math.min(100, familiarity);
  return `
    <div class="rel-bar-compact">
      <span class="rel-icon">❤️</span>
      <span class="rel-label-c">好感</span>
      <div class="rel-track"><div class="rel-track-fill fav-fill" style="width:${favPct}%"></div></div>
      <span class="rel-num">${favorability}</span>
    </div>
    <div class="rel-bar-compact">
      <span class="rel-icon">👋</span>
      <span class="rel-label-c">熟悉</span>
      <div class="rel-track"><div class="rel-track-fill fam-fill" style="width:${famPct}%"></div></div>
      <span class="rel-num">${familiarity}</span>
    </div>`;
}
