/**
 * Panel 1: Top bar - game title, clock, weather.
 */
const TopBar = {
  init() {
    Store.on('gameTime', (t) => this.update(t));
    Store.on('weather', (w) => this.updateWeather(w));
  },

  update(t) {
    if (!t) return;
    const clockEl = document.getElementById('gameClock');
    const seasonEl = document.getElementById('gameSeason');
    const phaseEl = document.getElementById('gamePhase');
    if (clockEl) clockEl.textContent = t.time_str || `Day ${t.day} · ${String(t.hour).padStart(2,'0')}:${String(t.minute).padStart(2,'0')}`;
    if (seasonEl) {
      const seasonMap = { spring: '🌱 春天', summer: '☀️ 夏天', autumn: '🍂 秋天', winter: '❄️ 冬天' };
      seasonEl.textContent = seasonMap[t.season] || t.season;
    }
    if (phaseEl) {
      const phaseMap = { dawn: '🌅 黎明', morning: '☀️ 早晨', noon: '🌞 中午', afternoon: '🌤️ 下午', evening: '🌆 傍晚', night: '🌙 夜晚', late_night: '🌃 深夜' };
      phaseEl.textContent = phaseMap[t.phase] || t.phase;
    }
  },

  updateWeather(w) {
    if (!w) return;
    const el = document.getElementById('weatherBadge');
    if (el) el.innerHTML = `<span class="weather-icon">${w.emoji || '☀️'}</span><span class="weather-text">${w.type || '晴天'}</span>`;
  },
};
