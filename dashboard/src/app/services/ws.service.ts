import { Injectable, OnDestroy } from '@angular/core';
import { Subject } from 'rxjs';
import { Event } from '../models';

@Injectable({ providedIn: 'root' })
export class WsService implements OnDestroy {
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = true;
  private unreadCount = 0;

  private alertSubject  = new Subject<Event>();
  private statusSubject = new Subject<'connected' | 'disconnected'>();
  private countSubject  = new Subject<number>();

  readonly alerts$  = this.alertSubject.asObservable();
  readonly status$  = this.statusSubject.asObservable();
  readonly unread$  = this.countSubject.asObservable();

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.ws = new WebSocket(`${protocol}//${location.host}/ws/alerts`);

    this.ws.onopen = () => {
      this.statusSubject.next('connected');
    };

    this.ws.onmessage = (e: MessageEvent) => {
      try {
        const event: Event = JSON.parse(e.data);
        this.unreadCount++;
        this.countSubject.next(this.unreadCount);
        this.alertSubject.next(event);
      } catch {
        /* ignore malformed frames */
      }
    };

    this.ws.onclose = () => {
      this.statusSubject.next('disconnected');
      if (this.shouldReconnect) {
        this.reconnectTimer = setTimeout(() => this.connect(), 3000);
      }
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  resetUnread(): void {
    this.unreadCount = 0;
    this.countSubject.next(0);
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }

  ngOnDestroy(): void {
    this.disconnect();
  }
}
