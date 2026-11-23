export const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

export type ApiStatus = 'ok' | 'setup_required' | 'degraded' | 'offline';
export type CrowdLevel = 'low' | 'moderate' | 'high' | 'seats_available' | 'standing_room' | 'crowded' | 'insufficient_data';

export interface Health {
  status: ApiStatus;
  database_ready: boolean;
  live_feed_configured?: boolean;
  operator_login_configured?: boolean;
  live_feed_status?: string;
  poll_interval_seconds?: number;
  record_counts?: Record<string, number>;
  metadata?: Record<string, string>;
}
export interface TicketSummary {
  total_records?: number;
  route_match_percentage?: number;
  missing_vehicle_number_records?: number;
  missing_vehicle_number_percentage?: number;
  boarding_stop_match_percentage?: number;
  alighting_stop_match_percentage?: number;
  date_range?: { start?: string; end?: string };
  od_groups_expanded_to_segments?: number;
  methodology_note?: string;
}
export interface Meta {
  product: string;
  counts: Record<string, number>;
  ticket_summary: TicketSummary;
}
export interface Route {
  route_id: string;
  agency_id?: string;
  route_short_name?: string;
  route_long_name?: string;
  route_desc?: string;
  route_type?: string;
}
export interface Stop {
  stop_id: string;
  stop_code?: string;
  stop_name: string;
  stop_lat?: number;
  stop_lon?: number;
}
export interface CrowdEstimate {
  level: CrowdLevel;
  label?: string;
  passenger_journeys_median?: number;
  estimated_ticketed_passengers_per_bus?: number | null;
  scheduled_departures_in_hour?: number;
  seat_capacity?: number | null;
  standing_capacity?: number | null;
  total_capacity?: number | null;
  capacity_configured?: boolean;
  capacity_source?: 'operator_verified' | 'dilliflow_planning_baseline' | string;
  estimated_occupied_seats?: number | null;
  estimated_available_seats?: number;
  estimated_occupied_standing_spaces?: number | null;
  estimated_available_standing_spaces?: number;
  availability_basis?: 'route_ticket_history' | 'segment_ticket_history' | 'network_reference' | 'route_level_fallback' | 'capacity_only_fallback' | string;
  availability_is_estimate?: boolean;
  relative_level?: 'low' | 'moderate' | 'high';
  sample_size?: number;
  observed_days?: number;
  confidence?: 'low' | 'medium' | 'high';
  coverage?: number;
  vehicle_id_coverage_pct?: number;
  period?: string;
  note?: string;
  estimate_basis?: string;
  departure_count_hour?: number;
  used_fallback?: string | null;
}
export interface Vehicle {
  vehicle_id: string;
  route_id: string;
  route_short_name?: string;
  route_long_name?: string;
  latitude: number;
  longitude: number;
  speed_mps?: number | null;
  speed_estimate_mps?: number | null;
  speed_source?: string;
  bearing?: number | null;
  bearing_estimate?: number | null;
  bearing_difference_degrees?: number | null;
  direction_aligned?: boolean;
  timestamp?: number | null;
  age_seconds?: number | null;
  freshness: 'fresh' | 'delayed' | 'stale' | 'unknown' | 'future_timestamp';
  trip_id?: string | null;
  eta_to_board_minutes?: number | null;
  estimated_arrival_at_boarding?: string | null;
  eta_confidence?: 'low' | 'medium' | 'unavailable';
  distance_to_board_m?: number | null;
  has_passed_boarding_stop?: boolean;
  at_boarding_stop?: boolean;
  approach_status?: 'at_boarding_stop' | 'approaching' | 'passed_boarding_stop' | 'near_boarding_stop_unconfirmed' | 'direction_unverified' | 'speed_unavailable' | 'on_route_eta_out_of_range';
  approach_message?: string;
  stop_id?: string | null;
  progress_percent?: number;
  current_stop_id?: string | null;
  current_stop_name?: string | null;
  last_passed_stop_id?: string | null;
  last_passed_stop_name?: string | null;
  last_passed_stop_sequence?: number | null;
  next_stop_id?: string | null;
  next_stop_name?: string | null;
  next_stop_sequence?: number | null;
  distance_to_next_stop_m?: number | null;
  progress_source?: 'gtfs_stop_id' | 'gps_shape_projection' | string;
  straight_line_distance_to_board_m?: number;
  cross_track_distance_m?: number;
  schedule_relationship?: string | null;
  matches_selected_scheduled_trip?: boolean;
  crowding?: CrowdEstimate;
  stop_arrivals?: Array<{
    stop_id: string;
    stop_name: string;
    stop_sequence: number;
    eta_minutes: number;
    estimated_arrival_at: string;
    crowding_to_next?: CrowdEstimate | null;
    crowding_source?: string;
    arrival_source?: 'gps_confirmed_stop' | 'gps_shape_projection' | string;
  }>;
}
export interface CrowdSegment {
  from_stop_id: string;
  to_stop_id: string;
  from_stop_name: string;
  to_stop_name: string;
  average_passenger_journeys: number | null;
  ticket_count: number;
  observed_days: number;
  crowding: CrowdEstimate;
}

export interface StopAdjacentSegment {
  from_stop_id: string;
  from_stop_name: string;
  to_stop_id: string;
  to_stop_name: string;
  crowding: CrowdEstimate;
}

export interface StopServedRoute {
  route_id: string;
  route_short_name?: string;
  route_long_name?: string;
  stop_sequence: number;
  crowding: CrowdEstimate;
  previous_segment?: StopAdjacentSegment | null;
  next_segment?: StopAdjacentSegment | null;
}

export interface StopCrowdingDetails {
  stop: Stop;
  routes: StopServedRoute[];
  routes_count: number;
  hour: number;
  day_type: string;
  period: string;
  methodology: string;
}

export interface LiveSnapshot {
  status: 'connected' | 'not_configured' | 'error' | 'degraded';
  message?: string;
  vehicles: Vehicle[];
  returned_count: number;
  fetched_at?: string | null;
  feed_timestamp?: number | null;
}
export interface JourneyStop extends Stop {
  stop_sequence: number;
  arrival_time?: string | null;
  departure_time?: string | null;
  crowding_to_next?: CrowdEstimate | null;
  crowding_source?: string;
}
export interface JourneyLeg {
  route_id: string;
  route_short_name: string;
  route_long_name: string;
  trip_id: string;
  from_stop: Stop;
  to_stop: Stop;
  departure_time: string;
  arrival_time: string;
  duration_minutes: number;
  geometry: [number, number][];
  crowding?: CrowdEstimate;
  stops?: JourneyStop[];
  live_vehicles?: Vehicle[];
  live_feed_status?: 'connected' | 'not_configured' | 'error' | 'degraded' | string;
  live_feed_message?: string;
  live_feed_fetched_at?: string | null;
  live_trip_match_count?: number;
  live_route_vehicle_count?: number;
  live_schedule_context_note?: string;
  minutes_until_scheduled_departure?: number | null;
  live_arrivals_status?: 'connected' | 'not_configured' | 'error' | 'degraded' | 'date_not_current' | 'selected_time_passed' | string;
  live_arrivals_message?: string;
  live_route_pattern_note?: string;
  live_arrival_basis?: string;
  live_vehicle_match_basis?: string;
}
export interface Journey {
  id: string;
  type: 'direct' | 'one_transfer';
  legs: JourneyLeg[];
  duration_minutes: number;
  transfers: number;
  departure_time: string;
  arrival_time: string;
  transfer_stop?: Stop;
  transfer_buffer_minutes?: number;
  crowding?: CrowdLevel;
  recommendation_reason?: string;
}

export interface OperatorLoginResult {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  operator_id: string;
}
export interface OperatorCapacity {
  route_id: string;
  route_short_name?: string;
  route_long_name?: string;
  seat_capacity: number;
  standing_capacity: number;
  total_capacity?: number;
  updated_at?: string;
  updated_by?: string;
}
export interface OperatorSegment {
  route_id: string;
  route_short_name: string;
  route_long_name: string;
  direction: string;
  from_stop_id: string;
  from_stop_name: string;
  to_stop_id: string;
  to_stop_name: string;
  average_ticketed_demand: number;
  estimated_ticketed_passengers_per_bus: number | null;
  scheduled_departures_in_hour: number;
  ticket_count: number;
  observed_days: number;
  crowding: CrowdEstimate;
  capacity_configured: boolean;
  capacity_pressure_ratio: number | null;
  potential_extra_departures_per_hour: number | null;
  priority: 'high' | 'review' | 'monitor';
  recommendation: string;
}
export interface OperatorServiceRecommendation {
  priority: 'high' | 'review' | 'monitor';
  title: string;
  route_id: string;
  route_short_name: string;
  direction: string;
  segment: string;
  evidence: string;
  action: string;
  type: string;
}
export interface OperatorDashboard {
  period: { start?: string; end?: string };
  selected_hour: number;
  day_type: 'weekday' | 'weekend';
  summary: {
    ticket_records: number;
    route_matched_records: number;
    route_match_percentage: number;
    missing_vehicle_number_percentage: number;
    routes_with_ticket_data: number;
    capacity_profiles_configured: number;
    routes_near_capacity: number;
    boarding_stop_match_percentage?: number;
    alighting_stop_match_percentage?: number;
  };
  data_quality?: {
    route_match_percentage: number;
    boarding_stop_match_percentage: number;
    alighting_stop_match_percentage: number;
    missing_vehicle_number_percentage: number;
    total_ticket_records: number;
    matched_route_records: number;
    unmatched_route_records: number;
  };
  peak_hours: Array<{ hour: number; avg_ticketed_journeys: number; ticket_count: number; observed_days: number; routes: number }>;
  route_demand: Array<{ rank?: number; route_id: string; route_short_name: string; route_long_name: string; direction: string; average_ticketed_passengers_per_hour: number; estimated_ticketed_passengers_per_bus: number | null; scheduled_departures_in_hour: number; ticket_count: number; observed_days: number; crowding: CrowdEstimate; capacity_configured: boolean; capacity_pressure_ratio: number | null; potential_extra_departures_per_hour: number | null }>;
  priority_segments: OperatorSegment[];
  investigation_segments?: OperatorSegment[];
  service_recommendations?: OperatorServiceRecommendation[];
  segments_reviewed: number;
  capacity_profiles: number;
  methodology: string;
}

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...(init?.headers || {}) },
    });
  } catch {
    throw new ApiError('Cannot reach the DilliFlow API. Start the FastAPI backend on localhost:8000.');
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof payload.detail === 'string' ? payload.detail : `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
  return payload as T;
}

export const api = {
  health: () => request<Health>('/api/health'),
  meta: () => request<Meta>('/api/meta'),
  routes: (q = '', limit = 100) => request<{ items: Route[]; total: number }>(`/api/routes?q=${encodeURIComponent(q)}&limit=${limit}`),
  route: (id: string) => request<{ route: Route; stops: Array<Stop & { stop_sequence: number }>; geometry: [number, number][]; crowding: CrowdEstimate }>(`/api/routes/${encodeURIComponent(id)}`),
  stops: (q: string, limit = 12) => request<{ items: Stop[]; total: number; limit?: number; offset?: number }>(`/api/stops?q=${encodeURIComponent(q)}&limit=${Math.min(500, Math.max(1, limit))}`),
  liveVehicles: (refresh = false) => request<LiveSnapshot>(`/api/live-vehicles${refresh ? '?refresh=true' : ''}`),
  crowdingOverview: () => request<Record<string, unknown>>('/api/crowding/overview'),
  crowdingRoutes: (hour?: number, dayType?: string, q?: string) => {
    const params = new URLSearchParams();
    if (hour !== undefined) params.set('hour', String(hour));
    if (dayType) params.set('day_type', dayType);
    if (q) params.set('q', q);
    return request<{ items: Array<Route & { average_passenger_journeys: number; ticket_count: number; crowding: CrowdEstimate }>; hour: number; day_type: string }>(`/api/crowding/routes?${params}`);
  },
  stopCrowding: (stopId: string) => request<StopCrowdingDetails>(`/api/stops/${encodeURIComponent(stopId)}/crowding`),
  segments: (routeId: string, hour?: number, dayType?: string) => {
    const params = new URLSearchParams({ route_id: routeId });
    if (hour !== undefined) params.set('hour', String(hour));
    if (dayType) params.set('day_type', dayType);
    return request<{ route_id: string; items: CrowdSegment[]; hour: number; day_type: string; period: string }>(`/api/crowding/segments?${params}`);
  },
  trends: (dayType = 'weekday', routeId?: string) => {
    const params = new URLSearchParams({ day_type: dayType });
    if (routeId) params.set('route_id', routeId);
    return request<{ items: Array<{ hour: number; passenger_journeys: number; ticket_count: number; route_count: number }> }>(`/api/crowding/trends?${params}`);
  },
  dataQuality: () => request<TicketSummary>('/api/data-quality'),
  journeys: (origin: string, destination: string, date: string, time: string, maxTransfers = 1) => {
    const params = new URLSearchParams({ origin_stop_id: origin, destination_stop_id: destination, travel_date: date, departure_time: time, max_transfers: String(maxTransfers) });
    return request<{ items: Journey[]; message?: string; methodology?: string }>(`/api/journeys/search?${params}`);
  },
  operatorLogin: (operator_id: string, password: string) => request<OperatorLoginResult>('/api/operator/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ operator_id, password }) }),
  operatorDashboard: (token: string, hour: number, dayType: 'weekday' | 'weekend') => request<OperatorDashboard>(`/api/operator/dashboard?hour=${hour}&day_type=${dayType}`, { headers: { Authorization: `Bearer ${token}` } }),
  operatorCapacities: (token: string) => request<{ items: OperatorCapacity[] }>(`/api/operator/capacities`, { headers: { Authorization: `Bearer ${token}` } }),
  saveOperatorCapacity: (token: string, routeId: string, seat_capacity: number, standing_capacity: number) => request<OperatorCapacity>(`/api/operator/capacities/${encodeURIComponent(routeId)}`, { method: 'PUT', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ seat_capacity, standing_capacity }) }),
  deleteOperatorCapacity: (token: string, routeId: string) => request<{ deleted: boolean; route_id: string }>(`/api/operator/capacities/${encodeURIComponent(routeId)}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } }),
};
