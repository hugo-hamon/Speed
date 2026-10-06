// Same schedule and stop position as speed/traffic.py. Time zero is the start
// of the race, never page load or the time spent selecting a route.
export const STOP_FRACTION = .35;
export const TRAFFIC_NAMES = {signal:'Feu rouge',rail:'Train',bridge:'Pont levant'};

export function trafficState(edge, time) {
  const event=edge.traffic_event;
  if(!event)return {closed:false,remaining:0,phase:0};
  const phase=((Math.round((time+event.phase)*1e6)/1e6)%event.period+event.period)%event.period;
  return {closed:phase<event.closed_for,remaining:Math.max(0,event.closed_for-phase),phase};
}

export function edgeJourney(edge, departure) {
  const drive=edge.travel_time,stopAt=departure+drive*STOP_FRACTION;
  const wait=trafficState(edge,stopAt).remaining;
  return {drive,stopAt,wait,releaseAt:stopAt+wait,arrival:Math.round((departure+drive+wait)*1e6)/1e6};
}
