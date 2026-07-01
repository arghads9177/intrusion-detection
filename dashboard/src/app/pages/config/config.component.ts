import {
  Component, OnInit, ViewChild, ElementRef, AfterViewChecked,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';
import { Camera, Zone, Rules } from '../../models';

const KNOWN_CLASSES = ['dog', 'cat', 'bird', 'horse', 'cow', 'sheep'];
const CANVAS_W = 640;
const CANVAS_H = 480;

@Component({
  selector: 'app-config',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './config.component.html',
  styleUrl: './config.component.scss',
})
export class ConfigComponent implements OnInit, AfterViewChecked {
  cameras: Camera[] = [];
  selectedCameraId = '';

  zone: Zone | null = null;
  rules: Rules | null = null;

  /* Editable copies */
  editPolygon: [number, number][] = [];
  editZoneName = 'default';
  editRules: Omit<Rules, 'camera_id'> = {
    active_hours_start: '00:00',
    active_hours_end: '23:59',
    sensitivity: 0.4,
    suppressed_classes: [],
  };

  suppClassChecked: Record<string, boolean> = {};
  readonly knownClasses = KNOWN_CLASSES;

  loading   = false;
  saveOk    = false;
  saveErr   = '';
  activeTab: 'zone' | 'rules' = 'zone';

  @ViewChild('zoneCanvas') canvasRef!: ElementRef<HTMLCanvasElement>;
  private canvasNeedsRedraw = false;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.api.getCameras().subscribe(c => {
      this.cameras = c;
      if (c.length > 0) this.selectCamera(c[0].id);
    });
  }

  ngAfterViewChecked(): void {
    if (this.canvasNeedsRedraw) {
      this.canvasNeedsRedraw = false;
      this.redrawCanvas();
    }
  }

  selectCamera(id: string): void {
    this.selectedCameraId = id;
    this.zone  = null;
    this.rules = null;
    this.saveOk = false;
    this.saveErr = '';

    this.api.getZone(id).subscribe({
      next: z => {
        this.zone        = z;
        this.editPolygon = z.polygon.map(p => [p[0], p[1]] as [number, number]);
        this.editZoneName = z.zone_name;
        this.scheduleRedraw();
      },
    });

    this.api.getRules(id).subscribe({
      next: r => {
        this.rules = r;
        this.editRules = {
          active_hours_start: r.active_hours_start,
          active_hours_end:   r.active_hours_end,
          sensitivity:        r.sensitivity,
          suppressed_classes: [...r.suppressed_classes],
        };
        this.suppClassChecked = {};
        KNOWN_CLASSES.forEach(c => {
          this.suppClassChecked[c] = r.suppressed_classes.includes(c);
        });
      },
    });
  }

  /* Zone canvas interaction */
  onCanvasClick(evt: MouseEvent): void {
    const rect = this.canvasRef.nativeElement.getBoundingClientRect();
    const scaleX = CANVAS_W / rect.width;
    const scaleY = CANVAS_H / rect.height;
    const x = Math.round((evt.clientX - rect.left) * scaleX);
    const y = Math.round((evt.clientY - rect.top)  * scaleY);
    this.editPolygon.push([x, y]);
    this.scheduleRedraw();
  }

  removeLastPoint(): void {
    this.editPolygon.pop();
    this.scheduleRedraw();
  }

  clearPolygon(): void {
    this.editPolygon = [];
    this.scheduleRedraw();
  }

  /* Persistence */
  saveZone(): void {
    if (!this.selectedCameraId || this.editPolygon.length < 3) return;
    this.loading = true;
    this.saveErr = '';
    this.api.upsertZone(this.selectedCameraId, {
      polygon: this.editPolygon,
      zone_name: this.editZoneName,
    }).subscribe({
      next: () => { this.loading = false; this.saveOk = true; setTimeout(() => this.saveOk = false, 3000); },
      error: () => { this.loading = false; this.saveErr = 'Failed to save zone.'; },
    });
  }

  saveRules(): void {
    if (!this.selectedCameraId) return;
    this.loading = true;
    this.saveErr = '';
    this.editRules.suppressed_classes = KNOWN_CLASSES.filter(c => this.suppClassChecked[c]);
    this.api.upsertRules(this.selectedCameraId, this.editRules).subscribe({
      next: () => { this.loading = false; this.saveOk = true; setTimeout(() => this.saveOk = false, 3000); },
      error: () => { this.loading = false; this.saveErr = 'Failed to save rules.'; },
    });
  }

  toggleClass(cls: string): void {
    this.suppClassChecked[cls] = !this.suppClassChecked[cls];
  }

  sensitivityLabel(): string {
    const v = this.editRules.sensitivity;
    if (v < 0.3) return 'Low';
    if (v < 0.6) return 'Medium';
    return 'High';
  }

  private scheduleRedraw(): void {
    this.canvasNeedsRedraw = true;
  }

  private redrawCanvas(): void {
    if (!this.canvasRef) return;
    const canvas = this.canvasRef.nativeElement;
    const ctx    = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

    /* Background grid */
    ctx.strokeStyle = 'rgba(30,48,80,0.5)';
    ctx.lineWidth = 0.5;
    for (let x = 0; x <= CANVAS_W; x += 64) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, CANVAS_H); ctx.stroke();
    }
    for (let y = 0; y <= CANVAS_H; y += 48) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CANVAS_W, y); ctx.stroke();
    }

    const pts = this.editPolygon;
    if (pts.length === 0) return;

    /* Draw polygon fill + stroke */
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    if (pts.length >= 3) ctx.closePath();

    ctx.fillStyle   = 'rgba(59,130,246,0.15)';
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth   = 2;
    ctx.setLineDash([6, 4]);
    if (pts.length >= 3) ctx.fill();
    ctx.stroke();
    ctx.setLineDash([]);

    /* Line to cursor preview: draw edge to first point */
    if (pts.length >= 2) {
      ctx.strokeStyle = 'rgba(59,130,246,0.4)';
      ctx.lineWidth   = 1;
      ctx.setLineDash([3, 4]);
      ctx.beginPath();
      ctx.moveTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
      ctx.lineTo(pts[0][0], pts[0][1]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    /* Draw vertex handles */
    pts.forEach((p, idx) => {
      ctx.beginPath();
      ctx.arc(p[0], p[1], 6, 0, Math.PI * 2);
      ctx.fillStyle = idx === 0 ? '#22c55e' : '#3b82f6';
      ctx.fill();
      ctx.strokeStyle = '#080d1a';
      ctx.lineWidth = 2;
      ctx.stroke();

      /* Coordinate label */
      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px Inter, sans-serif';
      ctx.fillText(`${p[0]},${p[1]}`, p[0] + 8, p[1] - 4);
    });
  }
}
