import { Component, OnInit, OnDestroy } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule, DatePipe } from '@angular/common';
import { Subscription } from 'rxjs';
import { WsService } from './services/ws.service';

interface NavItem {
  path: string;
  label: string;
  icon: string;
  alertBadge?: boolean;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, CommonModule, DatePipe],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent implements OnInit, OnDestroy {
  wsConnected = false;
  unreadAlerts = 0;
  now = new Date();

  readonly navItems: NavItem[] = [
    { path: '/live',    label: 'Live View',     icon: 'live'    },
    { path: '/alerts',  label: 'Alert Feed',    icon: 'alert',  alertBadge: true },
    { path: '/events',  label: 'Event Log',     icon: 'log'     },
    { path: '/stats',   label: 'Statistics',    icon: 'chart'   },
    { path: '/config',  label: 'Configuration', icon: 'config'  },
    { path: '/cameras', label: 'Cameras',       icon: 'camera'  },
  ];

  private subs = new Subscription();

  constructor(private ws: WsService) {}

  ngOnInit(): void {
    setInterval(() => (this.now = new Date()), 1000);
    this.ws.connect();
    this.subs.add(
      this.ws.status$.subscribe(s => (this.wsConnected = s === 'connected'))
    );
    this.subs.add(
      this.ws.unread$.subscribe(n => (this.unreadAlerts = n))
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
    this.ws.disconnect();
  }

  onAlertsNav(): void {
    this.ws.resetUnread();
  }
}
