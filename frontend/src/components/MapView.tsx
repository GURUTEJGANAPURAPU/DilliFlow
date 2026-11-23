import { useEffect, useRef } from 'react';
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet';
import type { LatLngBoundsExpression } from 'leaflet';
import type { Vehicle } from '../lib/api';

interface MapViewProps {
  vehicles?: Vehicle[];
  stopMarkers?: Array<{ stop_id: string; stop_name: string; stop_lat?: number; stop_lon?: number; stop_sequence?: number }>;
  line?: [number, number][];
  fitPoints?: [number, number][];
  selectedVehicleId?: string | null;
  onVehicleSelect?: (vehicle: Vehicle) => void;
  followSelectedVehicle?: boolean;
  className?: string;
  zoom?: number;
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  const geometryKey = points.map((point) => `${point[0].toFixed(5)},${point[1].toFixed(5)}`).join(';');
  useEffect(() => {
    if (points.length > 1) {
      const bounds = points as LatLngBoundsExpression;
      map.fitBounds(bounds, { padding: [42, 42], maxZoom: 14 });
    } else if (points.length === 1) {
      map.setView(points[0], 14, { animate: true });
    }
    // The geometry signature keeps live-marker polling from resetting the user's map zoom.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, geometryKey]);
  return null;
}

function FocusVehicle({ vehicle, follow }: { vehicle?: Vehicle; follow: boolean }) {
  const map = useMap();
  const lastVehicleId = useRef<string | null>(null);
  const vehicleId = vehicle?.vehicle_id ?? null;
  const latitude = vehicle?.latitude ?? null;
  const longitude = vehicle?.longitude ?? null;
  useEffect(() => {
    if (!vehicle || latitude == null || longitude == null) return;
    const selectionChanged = lastVehicleId.current !== vehicleId;
    if (selectionChanged || follow) {
      map.flyTo([latitude, longitude], Math.max(map.getZoom(), 15), {
        animate: true,
        duration: 0.65,
      });
    }
    lastVehicleId.current = vehicleId;
  }, [map, vehicleId, latitude, longitude, follow, vehicle]);
  return null;
}

function vehicleColor(freshness: Vehicle['freshness']) {
  if (freshness === 'fresh') return '#167b65';
  if (freshness === 'delayed') return '#d58b32';
  return '#8b918c';
}

export default function MapView({ vehicles = [], stopMarkers = [], line = [], fitPoints = [], selectedVehicleId, onVehicleSelect, followSelectedVehicle = false, className = '', zoom = 12 }: MapViewProps) {
  // Only auto-fit explicit journey/route geometry. Live GPS updates must not reset a user's map zoom every poll.
  const stopPoints: [number, number][] = stopMarkers.filter((stop) => stop.stop_lat != null && stop.stop_lon != null).map((stop) => [Number(stop.stop_lat), Number(stop.stop_lon)]);
  const points = fitPoints.length ? fitPoints : line.length ? line : stopPoints;
  const selectedVehicle = vehicles.find((vehicle) => vehicle.vehicle_id === selectedVehicleId);
  return (
    <div className={`map-frame ${className}`}>
      <MapContainer center={[28.6139, 77.2090]} zoom={zoom} scrollWheelZoom className="leaflet-map">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url={import.meta.env.VITE_MAP_TILE_URL || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'}
        />
        <FitBounds points={points} />
        <FocusVehicle vehicle={selectedVehicle} follow={followSelectedVehicle} />
        {line.length > 1 && <Polyline positions={line} pathOptions={{ color: '#147d68', weight: 5, opacity: 0.9, lineCap: 'round' }} />}
        {stopMarkers.filter((stop) => stop.stop_lat != null && stop.stop_lon != null).map((stop, index) => (
          <CircleMarker key={`${stop.stop_id}-${index}`} center={[Number(stop.stop_lat), Number(stop.stop_lon)]} radius={index === 0 || index === stopMarkers.length - 1 ? 5.5 : 3.5} pathOptions={{ color: '#ffffff', weight: 1.4, fillColor: index === 0 ? '#177d68' : index === stopMarkers.length - 1 ? '#bd5b4e' : '#42685a', fillOpacity: 0.98 }}>
            <Popup><div className="map-popup"><strong>{stop.stop_name}</strong><span>{stop.stop_sequence != null ? `Stop ${stop.stop_sequence}` : stop.stop_id}</span></div></Popup>
          </CircleMarker>
        ))}
        {vehicles.map((vehicle) => (
          <CircleMarker
            key={vehicle.vehicle_id}
            center={[vehicle.latitude, vehicle.longitude]}
            radius={selectedVehicleId === vehicle.vehicle_id ? 10.5 : 6.5}
            pathOptions={{ color: selectedVehicleId === vehicle.vehicle_id ? '#0c4e3f' : '#ffffff', weight: selectedVehicleId === vehicle.vehicle_id ? 3 : 2, fillColor: vehicleColor(vehicle.freshness), fillOpacity: 0.98 }}
            eventHandlers={{ click: () => onVehicleSelect?.(vehicle) }}
          >
            {selectedVehicleId === vehicle.vehicle_id && <Tooltip permanent direction="top" offset={[0, -8]}>{vehicle.vehicle_id}</Tooltip>}
            <Popup>
              <div className="map-popup">
                <strong>{vehicle.route_short_name || vehicle.route_id || 'Delhi bus'}</strong>
                <span>{vehicle.vehicle_id}</span>
                <small>{vehicle.freshness === 'fresh' ? 'Fresh position' : vehicle.freshness === 'delayed' ? 'Delayed position' : 'Stale / unknown position'}</small>
                {vehicle.current_stop_name && <small>Current stop: {vehicle.current_stop_name}</small>}
                {vehicle.next_stop_name && <small>Next stop: {vehicle.next_stop_name}</small>}
                {vehicle.progress_percent != null && <small>Journey corridor: {Math.round(vehicle.progress_percent)}%</small>}
                {vehicle.eta_to_board_minutes != null && <small>Boarding stop ETA: {vehicle.eta_to_board_minutes} min</small>}
                {vehicle.crowding?.level && <small>Historical route demand: {vehicle.crowding.level}</small>}
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
      <div className="map-attribution-note">Map data © OpenStreetMap</div>
    </div>
  );
}
