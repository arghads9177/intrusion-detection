export interface Camera {
  id: string;
  name: string;
  rtsp_url: string;
  location_type: string;
  enabled: boolean;
}

export interface Zone {
  camera_id: string;
  zone_name: string;
  polygon: [number, number][];
}

export interface Rules {
  camera_id: string;
  active_hours_start: string;
  active_hours_end: string;
  sensitivity: number;
  suppressed_classes: string[];
}

export interface Event {
  id: string;
  camera_id: string;
  timestamp: string;
  object_class: string;
  confidence: number;
  bbox: number[];
  zone_id: string;
  track_id: number | null;
  snapshot_path: string;
  clip_path: string;
  rule_applied: string;
  status: string;
}

export interface EventsPage {
  total: number;
  skip: number;
  limit: number;
  items: Event[];
}

export interface PerCameraStats {
  camera_id: string;
  intrusions: number;
  suppressed: number;
}

export interface Stats {
  total_intrusions: number;
  total_suppressed: number;
  per_camera: PerCameraStats[];
}
