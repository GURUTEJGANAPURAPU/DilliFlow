import { Activity, CircleHelp } from 'lucide-react';
import type { CrowdEstimate, CrowdLevel } from '../lib/api';

const labels: Record<CrowdLevel, string> = {
  low: 'Less crowded (relative)',
  moderate: 'Moderate crowd (relative)',
  high: 'High crowd (relative)',
  seats_available: 'Seats likely available',
  standing_room: 'Standing room likely',
  crowded: 'Crowded',
  insufficient_data: 'Not enough data',
};

export default function CrowdBadge({ estimate, level, fallbackLabel }: { estimate?: CrowdEstimate; level?: CrowdLevel; fallbackLabel?: string }) {
  const current = estimate?.level || level || 'insufficient_data';
  const displayLabel = estimate?.label || (current === 'insufficient_data' && fallbackLabel ? fallbackLabel : labels[current]);
  const title = estimate?.note || (current === 'insufficient_data' && fallbackLabel ? 'A typical network or route reference is shown because no specific load estimate is attached to this result.' : labels[current]);
  return (
    <span className={`crowd-badge crowd-${current}`} title={title}>
      {current === 'insufficient_data' ? <CircleHelp size={13} /> : <Activity size={13} />}
      {displayLabel}
    </span>
  );
}
