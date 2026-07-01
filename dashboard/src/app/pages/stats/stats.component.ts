import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration, ChartData } from 'chart.js';
import {
  Chart,
  BarController, BarElement,
  DoughnutController, ArcElement,
  CategoryScale, LinearScale,
  Tooltip, Legend,
} from 'chart.js';
import { ApiService } from '../../services/api.service';
import { Stats } from '../../models';

Chart.register(
  BarController, BarElement,
  DoughnutController, ArcElement,
  CategoryScale, LinearScale,
  Tooltip, Legend,
);

@Component({
  selector: 'app-stats',
  standalone: true,
  imports: [CommonModule, BaseChartDirective],
  templateUrl: './stats.component.html',
  styleUrl: './stats.component.scss',
})
export class StatsComponent implements OnInit {
  stats: Stats | null = null;
  loading = true;
  lastRefresh: Date | null = null;

  /* Bar chart — per camera */
  barData: ChartData<'bar'> = {
    labels: [],
    datasets: [
      {
        label: 'Intrusions',
        data: [],
        backgroundColor: 'rgba(239,68,68,0.7)',
        borderColor: '#ef4444',
        borderWidth: 1,
        borderRadius: 4,
      },
      {
        label: 'Suppressed',
        data: [],
        backgroundColor: 'rgba(59,130,246,0.5)',
        borderColor: '#3b82f6',
        borderWidth: 1,
        borderRadius: 4,
      },
    ],
  };

  barOptions: ChartConfiguration<'bar'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: { color: '#94a3b8', font: { family: 'Inter', size: 12 } },
      },
      tooltip: {
        backgroundColor: '#111e35',
        borderColor: '#1e3050',
        borderWidth: 1,
        titleColor: '#f1f5f9',
        bodyColor: '#94a3b8',
      },
    },
    scales: {
      x: {
        ticks: { color: '#64748b', font: { family: 'Inter', size: 11 } },
        grid: { color: '#1e3050' },
      },
      y: {
        ticks: { color: '#64748b', font: { family: 'Inter', size: 11 } },
        grid: { color: '#1e3050' },
        beginAtZero: true,
      },
    },
  };

  /* Doughnut chart — totals */
  donutData: ChartData<'doughnut'> = {
    labels: ['Intrusions', 'Suppressed'],
    datasets: [
      {
        data: [0, 0],
        backgroundColor: ['rgba(239,68,68,0.75)', 'rgba(59,130,246,0.55)'],
        borderColor: ['#ef4444', '#3b82f6'],
        borderWidth: 2,
        hoverOffset: 6,
      },
    ],
  };

  donutOptions: ChartConfiguration<'doughnut'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: { color: '#94a3b8', font: { family: 'Inter', size: 12 }, padding: 16 },
      },
      tooltip: {
        backgroundColor: '#111e35',
        borderColor: '#1e3050',
        borderWidth: 1,
        titleColor: '#f1f5f9',
        bodyColor: '#94a3b8',
      },
    },
  };

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading = true;
    this.api.getStats().subscribe({
      next: s => {
        this.stats = s;
        this.buildCharts(s);
        this.loading = false;
        this.lastRefresh = new Date();
      },
      error: () => (this.loading = false),
    });
  }

  private buildCharts(s: Stats): void {
    /* Bar */
    this.barData = {
      ...this.barData,
      labels: s.per_camera.map(c => c.camera_id),
      datasets: [
        { ...this.barData.datasets[0], data: s.per_camera.map(c => c.intrusions) },
        { ...this.barData.datasets[1], data: s.per_camera.map(c => c.suppressed) },
      ],
    };
    /* Donut */
    this.donutData = {
      ...this.donutData,
      datasets: [{ ...this.donutData.datasets[0], data: [s.total_intrusions, s.total_suppressed] }],
    };
  }

  detectionRate(): string {
    if (!this.stats) return '—';
    const total = this.stats.total_intrusions + this.stats.total_suppressed;
    if (total === 0) return '0%';
    return ((this.stats.total_intrusions / total) * 100).toFixed(1) + '%';
  }
}
