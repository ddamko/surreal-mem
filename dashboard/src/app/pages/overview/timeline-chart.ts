import { Component, ElementRef, afterNextRender, effect, inject, input } from '@angular/core';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

type Series = Record<string, { day: string; n: number }[]>;

const SERIES_ORDER: { key: string; label: string; cssVar: string }[] = [
  { key: 'entity', label: 'Entities', cssVar: '--type-person' },
  { key: 'fact', label: 'Facts', cssVar: '--type-organization' },
  { key: 'message', label: 'Messages', cssVar: '--type-location' },
  { key: 'conversation', label: 'Conversations', cssVar: '--type-event' },
];

@Component({
  selector: 'app-timeline-chart',
  template: '',
  host: { class: 'block' },
})
export class TimelineChart {
  readonly series = input.required<Series>();
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private chart: echarts.ECharts | null = null;
  private observer: ResizeObserver | null = null;

  constructor() {
    afterNextRender(() => {
      this.chart = echarts.init(this.host.nativeElement, undefined, { renderer: 'canvas' });
      let pending = 0;
      this.observer = new ResizeObserver(() => {
        if (pending) return;
        pending = requestAnimationFrame(() => {
          pending = 0;
          this.chart?.resize();
        });
      });
      this.observer.observe(this.host.nativeElement);
      this.render();
    });
    effect(() => {
      this.series();
      this.render();
    });
  }

  private render(): void {
    if (!this.chart) return;
    const style = getComputedStyle(document.documentElement);
    const ink = style.getPropertyValue('--edge-ink').trim() || '#888';
    const days = new Set<string>();
    for (const rows of Object.values(this.series())) for (const r of rows) days.add(r.day);
    const axis = [...days].sort();
    this.chart.setOption({
      animationDuration: 300,
      grid: { left: 36, right: 12, top: 28, bottom: 28 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'line' } },
      legend: { top: 0, right: 0, textStyle: { color: ink }, itemWidth: 10, itemHeight: 2 },
      xAxis: { type: 'category', data: axis, axisLine: { lineStyle: { color: ink, opacity: 0.4 } }, axisLabel: { color: ink } },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: ink, opacity: 0.15 } }, axisLabel: { color: ink } },
      series: SERIES_ORDER.map(({ key, label, cssVar }) => {
        const byDay = new Map((this.series()[key] ?? []).map((r) => [r.day, r.n]));
        return {
          name: label,
          type: 'line',
          smooth: 0.2,
          showSymbol: false,
          lineStyle: { width: 2 },
          color: style.getPropertyValue(cssVar).trim(),
          data: axis.map((d) => byDay.get(d) ?? 0),
        };
      }),
    });
  }
}
