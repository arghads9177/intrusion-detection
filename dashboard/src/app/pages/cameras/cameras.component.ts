import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { Camera, Zone, Rules } from '../../models';

interface CameraDetail {
  camera: Camera;
  zone: Zone | null;
  rules: Rules | null;
  zoneLoaded: boolean;
  rulesLoaded: boolean;
}

@Component({
  selector: 'app-cameras',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './cameras.component.html',
  styleUrl: './cameras.component.scss',
})
export class CamerasComponent implements OnInit {
  details: CameraDetail[] = [];
  loading = true;
  expandedId: string | null = null;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.api.getCameras().subscribe({
      next: cams => {
        this.details = cams.map(c => ({
          camera: c,
          zone: null,
          rules: null,
          zoneLoaded: false,
          rulesLoaded: false,
        }));
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  toggleExpand(id: string): void {
    this.expandedId = this.expandedId === id ? null : id;
    const detail = this.details.find(d => d.camera.id === id);
    if (!detail || this.expandedId !== id) return;

    if (!detail.zoneLoaded) {
      this.api.getZone(id).subscribe({
        next: z  => { detail.zone = z; detail.zoneLoaded = true; },
        error: () => { detail.zoneLoaded = true; },
      });
    }
    if (!detail.rulesLoaded) {
      this.api.getRules(id).subscribe({
        next: r  => { detail.rules = r; detail.rulesLoaded = true; },
        error: () => { detail.rulesLoaded = true; },
      });
    }
  }

  isExpanded(id: string): boolean { return this.expandedId === id; }

  formatHours(rules: Rules): string {
    return `${rules.active_hours_start} – ${rules.active_hours_end}`;
  }

  polygonSummary(zone: Zone): string {
    return `${zone.polygon.length} vertices`;
  }
}
