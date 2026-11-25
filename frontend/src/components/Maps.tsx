import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect } from "react";
import { Circle, MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";

// Inline SVG pins (avoids broken default marker image paths under bundlers).
function pin(color: string) {
  return L.divIcon({
    className: "",
    iconSize: [28, 36],
    iconAnchor: [14, 34],
    popupAnchor: [0, -30],
    html: `<svg width="28" height="36" viewBox="0 0 28 36" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M14 1C7 1 1.5 6.4 1.5 13.2 1.5 22.5 14 35 14 35s12.5-12.5 12.5-21.8C26.5 6.4 21 1 14 1z" fill="${color}" stroke="#fff" stroke-width="2"/><circle cx="14" cy="13" r="5" fill="#fff"/></svg>`,
  });
}
export const pins = { pickup: pin("#246a35"), ngo: pin("#d99a06"), other: pin("#475569") };

const BLR: [number, number] = [12.9716, 77.5946];

function Tiles() {
  return <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />;
}

function ClickToSet({ onChange }: { onChange: (lat: number, lng: number) => void }) {
  useMapEvents({ click: (e) => onChange(+e.latlng.lat.toFixed(6), +e.latlng.lng.toFixed(6)) });
  return null;
}

function Recenter({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView([lat, lng], Math.max(map.getZoom(), 14));
  }, [lat, lng, map]);
  return null;
}

/** Map for choosing the pickup point: click or drag the pin. Number inputs are offered alongside for keyboard users. */
export function MapPicker({ lat, lng, onChange }: { lat: number | null; lng: number | null; onChange: (lat: number, lng: number) => void }) {
  const has = lat != null && lng != null;
  return (
    <div className="h-64 overflow-hidden rounded-lg border border-slate-300" aria-label="Pickup location map. Click to place the pin or drag it.">
      <MapContainer center={has ? [lat!, lng!] : BLR} zoom={has ? 14 : 11} className="h-full w-full" scrollWheelZoom={false}>
        <Tiles />
        <ClickToSet onChange={onChange} />
        {has && (
          <>
            <Recenter lat={lat!} lng={lng!} />
            <Marker
              position={[lat!, lng!]}
              icon={pins.pickup}
              draggable
              eventHandlers={{
                dragend: (e) => {
                  const p = (e.target as L.Marker).getLatLng();
                  onChange(+p.lat.toFixed(6), +p.lng.toFixed(6));
                },
              }}
            />
          </>
        )}
      </MapContainer>
    </div>
  );
}

export interface MapPoint {
  lat: number;
  lng: number;
  label: string;
  kind?: keyof typeof pins;
  approximate?: boolean;
}

export function MapView({ points, height = "h-64" }: { points: MapPoint[]; height?: string }) {
  if (!points.length) return null;
  const bounds = L.latLngBounds(points.map((p) => [p.lat, p.lng] as [number, number]));
  return (
    <div className={`${height} overflow-hidden rounded-lg border border-slate-300`}>
      <MapContainer bounds={bounds.pad(0.3)} className="h-full w-full" scrollWheelZoom={false}>
        <Tiles />
        {points.map((p, i) =>
          p.approximate ? (
            <Circle key={i} center={[p.lat, p.lng]} radius={900} pathOptions={{ color: "#246a35", fillOpacity: 0.15 }}>
              <Popup>{p.label} (approximate area - exact address shared after acceptance)</Popup>
            </Circle>
          ) : (
            <Marker key={i} position={[p.lat, p.lng]} icon={pins[p.kind ?? "other"]}>
              <Popup>{p.label}</Popup>
            </Marker>
          ),
        )}
      </MapContainer>
    </div>
  );
}
