import {
  Component, OnInit, OnDestroy, ViewChildren, QueryList,
  ElementRef, AfterViewInit, ChangeDetectorRef,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../services/api.service';
import { WsService } from '../../services/ws.service';
import { Camera, Event, Zone } from '../../models';
import { Subscription } from 'rxjs';

interface CameraState {
  camera: Camera;
  latestEvent: Event | null;
  zone: Zone | null;
  snapshotUrl: string | null;
  lastUpdate: Date | null;
  loading: boolean;
  alertFlash: boolean;
}

@Component({
  selector: 'app-live-view',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './live-view.component.html',
  styleUrl: './live-view.component.scss',
})
export class LiveViewComponent implements OnInit, OnDestroy, AfterViewInit {
  cameras: CameraState[] = [];
  loading = true;

  @ViewChildren('overlayCanvas') canvases!: QueryList<ElementRef<HTMLCanvasElement>>;
  @ViewChildren('snapImg') snapImgs!: QueryList<ElementRef<HTMLImageElement>>;

  private refreshInterval: ReturnType<typeof setInterval> | null = null;
  private sub = new Subscription();
  private readonly REFRESH_MS = 5000;

  constructor(
    private api: ApiService,
    private ws: WsService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.api.getCameras().subscribe({
      next: cams => {
        this.cameras = cams.map(c => ({
          camera: c,
          latestEvent: null,
          zone: null,
          snapshotUrl: null,
          lastUpdate: null,
          loading: true,
          alertFlash: false,
        }));
        this.loading = false;
        cams.forEach(c => this.loadCamera(c.id));
        this.startRefresh();
      },
    });

    /* Flash camera tile on new WS alert */
    this.sub.add(
      this.ws.alerts$.subscribe(ev => {
        const state = this.cameras.find(s => s.camera.id === ev.camera_id);
        if (state) {
          state.latestEvent = ev;
          state.snapshotUrl = this.api.snapshotUrl(ev.id) + '?t=' + Date.now();
          state.lastUpdate  = new Date();
          state.alertFlash  = true;
          this.cdr.detectChanges();
          setTimeout(() => {
            state.alertFlash = false;
            this.cdr.detectChanges();
            this.drawOverlay(ev.camera_id);
          }, 2000);
          this.drawOverlay(ev.camera_id);
        }
      }),
    );
  }

  ngAfterViewInit(): void {
    this.canvases.changes.subscribe(() => {
      this.cameras.forEach(s => this.drawOverlay(s.camera.id));
    });
  }

  ngOnDestroy(): void {
    if (this.refreshInterval) clearInterval(this.refreshInterval);
    this.sub.unsubscribe();
  }

  private loadCamera(cameraId: string): void {
    const state = this.cameras.find(s => s.camera.id === cameraId);
    if (!state) return;

    /* Load zone */
    this.api.getZone(cameraId).subscribe({
      next: z => {
        state.zone = z;
        this.drawOverlay(cameraId);
      },
    });

    /* Load latest event snapshot */
    this.api.getLatestEvent(cameraId).subscribe({
      next: page => {
        if (page.items.length > 0) {
          const ev = page.items[0];
          state.latestEvent = ev;
          state.snapshotUrl = this.api.snapshotUrl(ev.id) + '?t=' + Date.now();
          state.lastUpdate  = new Date(ev.timestamp);
        }
        state.loading = false;
        this.cdr.detectChanges();
        this.drawOverlay(cameraId);
      },
      error: () => {
        state.loading = false;
        this.cdr.detectChanges();
      },
    });
  }

  private startRefresh(): void {
    this.refreshInterval = setInterval(() => {
      this.cameras.forEach(s => this.loadCamera(s.camera.id));
    }, this.REFRESH_MS);
  }

  drawOverlay(cameraId: string): void {
    const idx = this.cameras.findIndex(s => s.camera.id === cameraId);
    if (idx < 0 || !this.canvases) return;

    const canvasArr = this.canvases.toArray();
    if (!canvasArr[idx]) return;

    const canvas = canvasArr[idx].nativeElement;
    const state  = this.cameras[idx];
    const ctx    = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const zone = state.zone;
    if (!zone || zone.polygon.length < 3) return;

    const W = canvas.width;
    const H = canvas.height;
    const FRAME_W = 640;
    const FRAME_H = 480;
    const scaleX = W / FRAME_W;
    const scaleY = H / FRAME_H;

    /* Draw zone polygon */
    ctx.beginPath();
    ctx.moveTo(zone.polygon[0][0] * scaleX, zone.polygon[0][1] * scaleY);
    for (let i = 1; i < zone.polygon.length; i++) {
      ctx.lineTo(zone.polygon[i][0] * scaleX, zone.polygon[i][1] * scaleY);
    }
    ctx.closePath();
    ctx.fillStyle   = 'rgba(59,130,246,0.12)';
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth   = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.fill();
    ctx.stroke();
    ctx.setLineDash([]);

    /* Zone label */
    ctx.fillStyle = '#3b82f6';
    ctx.font = 'bold 11px Inter, sans-serif';
    ctx.fillText(zone.zone_name, zone.polygon[0][0] * scaleX + 6, zone.polygon[0][1] * scaleY - 6);

    /* Latest event bbox */
    const ev = state.latestEvent;
    if (ev && ev.bbox?.length === 4) {
      const [x1, y1, x2, y2] = ev.bbox;
      const bx = x1 * scaleX, by = y1 * scaleY;
      const bw = (x2 - x1) * scaleX, bh = (y2 - y1) * scaleY;

      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth   = 2;
      ctx.strokeRect(bx, by, bw, bh);

      /* Label background */
      const label = `${ev.object_class} ${(ev.confidence * 100).toFixed(0)}%`;
      ctx.font = 'bold 11px Inter, sans-serif';
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = 'rgba(127,29,29,0.85)';
      ctx.fillRect(bx, by - 20, tw + 8, 18);
      ctx.fillStyle = '#fca5a5';
      ctx.fillText(label, bx + 4, by - 6);
    }
  }

  onSnapLoad(cameraId: string): void {
    this.drawOverlay(cameraId);
  }

  trackByCamera(_: number, s: CameraState): string { return s.camera.id; }
}
