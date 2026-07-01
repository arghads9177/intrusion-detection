import { Component, OnInit } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, EventFilters } from '../../services/api.service';
import { Event, Camera } from '../../models';

@Component({
  selector: 'app-event-log',
  standalone: true,
  imports: [CommonModule, DatePipe, FormsModule],
  templateUrl: './event-log.component.html',
  styleUrl: './event-log.component.scss',
})
export class EventLogComponent implements OnInit {
  events: Event[] = [];
  total    = 0;
  loading  = false;

  cameras: Camera[] = [];
  filters: EventFilters = { skip: 0, limit: 20 };

  /* filter form state */
  filterCamera = '';
  filterClass  = '';
  filterAfter  = '';
  filterBefore = '';

  selectedEvent: Event | null = null;

  readonly PAGE_SIZE = 20;
  readonly classes = ['person', 'dog', 'cat', 'bird', 'horse'];

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.api.getCameras().subscribe(c => (this.cameras = c));
    this.load();
  }

  load(): void {
    this.loading = true;
    const f: EventFilters = {
      skip:  this.filters.skip,
      limit: this.PAGE_SIZE,
    };
    if (this.filterCamera) f.camera_id    = this.filterCamera;
    if (this.filterClass)  f.object_class = this.filterClass;
    if (this.filterAfter)  f.after        = new Date(this.filterAfter).toISOString();
    if (this.filterBefore) f.before       = new Date(this.filterBefore).toISOString();

    this.api.getEvents(f).subscribe({
      next: page => {
        this.events  = page.items;
        this.total   = page.total;
        this.loading = false;
      },
      error: () => (this.loading = false),
    });
  }

  applyFilters(): void {
    this.filters.skip = 0;
    this.load();
  }

  clearFilters(): void {
    this.filterCamera = '';
    this.filterClass  = '';
    this.filterAfter  = '';
    this.filterBefore = '';
    this.filters.skip = 0;
    this.load();
  }

  prevPage(): void {
    if ((this.filters.skip ?? 0) >= this.PAGE_SIZE) {
      this.filters.skip = (this.filters.skip ?? 0) - this.PAGE_SIZE;
      this.load();
    }
  }

  nextPage(): void {
    const skip = (this.filters.skip ?? 0) + this.PAGE_SIZE;
    if (skip < this.total) {
      this.filters.skip = skip;
      this.load();
    }
  }

  get currentPage(): number { return Math.floor((this.filters.skip ?? 0) / this.PAGE_SIZE) + 1; }
  get totalPages(): number  { return Math.ceil(this.total / this.PAGE_SIZE) || 1; }

  openEvent(ev: Event): void { this.selectedEvent = ev; }
  closeModal(): void          { this.selectedEvent = null; }

  snapshotUrl(id: string) { return this.api.snapshotUrl(id); }
  clipUrl(id: string)     { return this.api.clipUrl(id); }
  confidence(ev: Event)   { return (ev.confidence * 100).toFixed(1) + '%'; }
}
