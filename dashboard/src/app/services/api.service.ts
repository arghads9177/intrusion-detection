import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Camera, Zone, Rules, Event, EventsPage, Stats } from '../models';

export interface EventFilters {
  camera_id?: string;
  object_class?: string;
  after?: string;
  before?: string;
  skip?: number;
  limit?: number;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly base = '/api';

  constructor(private http: HttpClient) {}

  /* ── Cameras ── */
  getCameras() {
    return this.http.get<Camera[]>(`${this.base}/cameras`);
  }

  /* ── Zone ── */
  getZone(cameraId: string) {
    return this.http.get<Zone>(`${this.base}/cameras/${cameraId}/zone`);
  }

  upsertZone(cameraId: string, payload: { polygon: [number, number][]; zone_name?: string }) {
    return this.http.put<Zone>(`${this.base}/cameras/${cameraId}/zone`, payload);
  }

  /* ── Rules ── */
  getRules(cameraId: string) {
    return this.http.get<Rules>(`${this.base}/cameras/${cameraId}/rules`);
  }

  upsertRules(cameraId: string, payload: Omit<Rules, 'camera_id'>) {
    return this.http.put<Rules>(`${this.base}/cameras/${cameraId}/rules`, payload);
  }

  /* ── Events ── */
  getEvents(filters: EventFilters = {}) {
    let params = new HttpParams();
    if (filters.camera_id)   params = params.set('camera_id', filters.camera_id);
    if (filters.object_class) params = params.set('object_class', filters.object_class);
    if (filters.after)       params = params.set('after', filters.after);
    if (filters.before)      params = params.set('before', filters.before);
    params = params.set('skip',  String(filters.skip  ?? 0));
    params = params.set('limit', String(filters.limit ?? 20));
    return this.http.get<EventsPage>(`${this.base}/events`, { params });
  }

  getLatestEvent(cameraId: string) {
    return this.getEvents({ camera_id: cameraId, limit: 1 });
  }

  /* ── Stats ── */
  getStats() {
    return this.http.get<Stats>(`${this.base}/stats`);
  }

  /* ── Media URLs ── */
  snapshotUrl(eventId: string) {
    return `${this.base}/events/${eventId}/snapshot`;
  }

  clipUrl(eventId: string) {
    return `${this.base}/events/${eventId}/clip`;
  }
}
