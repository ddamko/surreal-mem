import { Directive, ElementRef, afterNextRender, effect, inject, input } from '@angular/core';
import * as echarts from 'echarts/core';
import { BarChart, HeatmapChart, LineChart, SankeyChart, ScatterChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { themeColor } from './color';

echarts.use([BarChart, LineChart, SankeyChart, HeatmapChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, CanvasRenderer]);

export function chartInk(): { ink: string; text: string; primary: string } {
  return {
    ink: themeColor('--edge-ink', '#888888'),
    text: themeColor('--color-base-content', '#dddddd'),
    primary: themeColor('--color-primary', '#e8b04b'),
  };
}

/** `<div appChart [option]="..."></div>`: owns an ECharts instance and resizes with its host. */
@Directive({ selector: '[appChart]' })
export class ChartDirective {
  readonly option = input.required<echarts.EChartsCoreOption | null>({ alias: 'appChart' });
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private chart: echarts.ECharts | null = null;

  constructor() {
    afterNextRender(() => {
      this.chart = echarts.init(this.host.nativeElement, undefined, { renderer: 'canvas' });
      const observer = new ResizeObserver(() => this.chart?.resize());
      observer.observe(this.host.nativeElement);
      this.apply();
    });
    effect(() => {
      this.option();
      this.apply();
    });
  }

  private apply(): void {
    const option = this.option();
    if (this.chart && option) this.chart.setOption(option, true);
  }
}
