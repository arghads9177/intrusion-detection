import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { Subscription } from 'rxjs';
import { WsService } from '../../services/ws.service';
import { ApiService } from '../../services/api.service';
import { Event } from '../../models';

@Component({
  selector: 'app-alert-feed',
  standalone: true,
  imports: [CommonModule, DatePipe],
  templateUrl: './alert-feed.component.html',
  styleUrl: './alert-feed.component.scss',
})
export class AlertFeedComponent implements OnInit, OnDestroy {
  alerts: (Event & { _new?: boolean })[] = [];
  maxAlerts = 50;
  selectedAlert: Event | null = null;

  private sub = new Subscription();

  constructor(
    private ws: WsService,
    private api: ApiService,
  ) {}

  ngOnInit(): void {
    this.ws.resetUnread();

    /* Pre-populate from REST so the feed isn't empty on load */
    this.api.getEvents({ limit: 20 }).subscribe({
      next: page => {
        this.alerts = page.items.map(e => ({ ...e, _new: false }));
      },
    });

    /* Subscribe to live WS alerts */
    this.sub.add(
      this.ws.alerts$.subscribe(ev => {
        const entry = { ...ev, _new: true };
        this.alerts.unshift(entry);
        if (this.alerts.length > this.maxAlerts) {
          this.alerts = this.alerts.slice(0, this.maxAlerts);
        }
        setTimeout(() => (entry._new = false), 2000);
      }),
    );
  }

  ngOnDestroy(): void {
    this.sub.unsubscribe();
  }

  openAlert(ev: Event): void {
    this.selectedAlert = ev;
  }

  closeModal(): void {
    this.selectedAlert = null;
  }

  snapshotUrl(id: string) { return this.api.snapshotUrl(id); }
  clipUrl(id: string)     { return this.api.clipUrl(id); }

  confidence(ev: Event): string {
    return (ev.confidence * 100).toFixed(0) + '%';
  }
}
