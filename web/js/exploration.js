import { explorationProgress } from './state.js';

export const ROUTE_REVEAL_SECONDS = 1.8;
export const HEAT_FADE_SECONDS = .4;
// Dijkstra: durée de maintien avant le fondu, en secondes.
export const DIJKSTRA_TRAIL_MIN_SECONDS = .8;
export const DIJKSTRA_TRAIL_MAX_SECONDS = 5;

// Only consumed events contribute to the heat map. Keep this history across
// frames, but rebuild it when replaying, rewinding or starting another search.
export function updateExploration(previous, state, time) {
  const events = state.ai.events;
  const count = Math.floor(explorationProgress(state, time) * events.length);
  let history = previous;
  if (!history || history.events !== events || count < history.count) {
    history = { events, count: 0, visits: new Map(), heat: new Map(), route: [state.start], routeAt: [] };
  }
  for (let i = history.count; i < count; i++) {
    const event = events[i], visit = history.visits.get(event.node);
    const at = (i + 1) / events.length * state.exploreDuration;
    history.visits.set(event.node, {
      count: (visit?.count || 0) + 1,
      first: visit?.first ?? (i + 1) / events.length * state.exploreDuration,
    });
    if (event.kind === 'advance' || event.kind === 'backtrack') {
      // A local decision ends this search wave. Its colours fade while the
      // orange route advances; the next wave starts with fresh intensities.
      for (const cell of history.heat.values()) cell.retiredAt ??= at;
      history.route.push(event.node);
      history.routeAt.push(at);
    } else {
      const cell = history.heat.get(event.node);
      const active = cell && cell.retiredAt === undefined;
      history.heat.set(event.node, {
        count: active ? cell.count + 1 : 1,
        first: active ? cell.first : at,
        last: at,
      });
    }
  }
  history.count = count;
  return history;
}

// All fades use the algorithm clock, so Pause freezes both colour and route.
export function heatOpacity(cell, state, time, reducedMotion = false) {
  const clock = state.aiPaused ? state.aiPauseTime : time;
  const elapsed = clock - state.exploreStarted;
  let end = Math.min(cell.retiredAt ?? Infinity, state.exploreDuration);
  if (state.map.ai_type === 'dijkstra') {
    const trail = Math.max(DIJKSTRA_TRAIL_MIN_SECONDS, Math.min(DIJKSTRA_TRAIL_MAX_SECONDS, state.exploreDuration / Math.max(1, state.ai.events.length) * 3));
    end = Math.min(end, cell.last + trail);
  }
  if (reducedMotion) return elapsed < end ? 1 : 0;
  const appear = Math.max(0, Math.min(1, (elapsed - cell.first) / .15));
  const disappear = Math.max(0, Math.min(1, 1 - (elapsed - end) / HEAT_FADE_SECONDS));
  return appear * disappear;
}

export function routeRevealProgress(state, time) {
  const clock = state.aiPaused ? state.aiPauseTime : time;
  return Math.max(0, Math.min(1, (clock - state.exploreStarted - state.exploreDuration) / ROUTE_REVEAL_SECONDS));
}
