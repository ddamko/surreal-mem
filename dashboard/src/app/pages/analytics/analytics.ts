import { DecimalPipe, KeyValuePipe } from '@angular/common';
import { Component, computed, inject, resource, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import type { EChartsCoreOption } from 'echarts/core';
import { ApiService } from '../../core/api';
import { ChartDirective, chartInk } from '../../core/charts';
import { SpaceService } from '../../core/space';
import { BASE_TYPES, typeColor } from '../../core/types';

type Row = Record<string, unknown>;

@Component({
  selector: 'app-analytics',
  imports: [ChartDirective, DecimalPipe, KeyValuePipe, RouterLink],
  templateUrl: './analytics.html',
})
export class AnalyticsPage {
  private readonly api = inject(ApiService);
  protected readonly space = inject(SpaceService);
  protected readonly typeColor = typeColor;
  protected readonly metric = signal<'pagerank' | 'degree' | 'betweenness'>('pagerank');

  private rows(path: '/api/v1/analytics/centrality' | '/api/v1/analytics/communities' | '/api/v1/analytics/kinds' | '/api/v1/analytics/flows' | '/api/v1/analytics/cooccurrence', extra: Record<string, unknown> = {}) {
    return resource({
      params: () => ({ space: this.space.param(), metric: this.metric(), ...extra }),
      loader: async ({ params }) => {
        const { data, error } = await this.api.client.GET(path, { params: { query: { space: params.space, metric: params.metric, limit: 25 } as never } });
        if (error) throw error;
        return (data as { rows: Row[] }).rows;
      },
    });
  }

  protected readonly centrality = this.rows('/api/v1/analytics/centrality');
  protected readonly communities = this.rows('/api/v1/analytics/communities');
  protected readonly kinds = this.rows('/api/v1/analytics/kinds');
  protected readonly flows = this.rows('/api/v1/analytics/flows');
  protected readonly cooccurrence = this.rows('/api/v1/analytics/cooccurrence');
  protected readonly health = resource({
    params: () => ({ space: this.space.param() }),
    loader: async ({ params }) => {
      const { data, error } = await this.api.client.GET('/api/v1/analytics/facts', { params: { query: { space: params.space } } });
      if (error) throw error;
      return data as { by_status: Record<string, number>; confidence: { bucket: number; n: number }[]; salience: { bucket: number; n: number }[]; contradictions: Row[]; flagged: number };
    },
  });

  private val<T>(r: { hasValue(): boolean; value(): T }): T | null {
    return r.hasValue() ? r.value() : null;
  }

  protected readonly centralityOption = computed<EChartsCoreOption | null>(() => {
    const rows = this.val(this.centrality);
    if (!rows?.length) return null;
    const { ink, text } = chartInk();
    const data = [...rows].reverse();
    return {
      grid: { left: 150, right: 24, top: 8, bottom: 24 },
      tooltip: { trigger: 'item', formatter: (p: { name: string; value: number }) => `${p.name}: ${p.value.toFixed(4)}` },
      xAxis: { type: 'value', axisLabel: { color: ink }, splitLine: { lineStyle: { color: ink, opacity: 0.15 } } },
      yAxis: { type: 'category', data: data.map((r) => String(r['name'])), axisLabel: { color: text, width: 140, overflow: 'truncate' }, axisLine: { show: false }, axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: 10, itemStyle: { borderRadius: [0, 4, 4, 0], color: (p: { dataIndex: number }) => typeColor(String(data[p.dataIndex]['base_type'])) }, data: data.map((r) => Number(r['value'])) }],
    };
  });

  protected readonly kindsOption = computed<EChartsCoreOption | null>(() => {
    const rows = this.val(this.kinds);
    if (!rows?.length) return null;
    const { ink, text, primary } = chartInk();
    const data = [...rows].sort((a, b) => Number(a['n']) - Number(b['n'])).slice(-20);
    return {
      grid: { left: 130, right: 24, top: 8, bottom: 24 },
      tooltip: { trigger: 'item' },
      xAxis: { type: 'value', axisLabel: { color: ink }, splitLine: { lineStyle: { color: ink, opacity: 0.15 } } },
      yAxis: { type: 'category', data: data.map((r) => String(r['kind'])), axisLabel: { color: text, fontFamily: 'JetBrains Mono Variable' }, axisLine: { show: false }, axisTick: { show: false } },
      series: [{ type: 'bar', barWidth: 10, itemStyle: { color: primary, borderRadius: [0, 4, 4, 0] }, data: data.map((r) => Number(r['n'])) }],
    };
  });

  protected readonly flowsOption = computed<EChartsCoreOption | null>(() => {
    const rows = this.val(this.flows);
    if (!rows?.length) return null;
    const { text } = chartInk();
    const nodes = new Map<string, { name: string; itemStyle: { color: string } }>();
    const links: { source: string; target: string; value: number }[] = [];
    for (const r of rows) {
      const s = `${r['source']} →`, t = `→ ${r['target']}`;
      nodes.set(s, { name: s, itemStyle: { color: typeColor(String(r['source'])) } });
      nodes.set(t, { name: t, itemStyle: { color: typeColor(String(r['target'])) } });
      const existing = links.find((l) => l.source === s && l.target === t);
      if (existing) existing.value += Number(r['n']);
      else links.push({ source: s, target: t, value: Number(r['n']) });
    }
    return {
      tooltip: { trigger: 'item' },
      series: [{ type: 'sankey', left: 8, right: 90, top: 8, bottom: 8, nodeWidth: 10, nodeGap: 12, emphasis: { focus: 'adjacency' }, label: { color: text }, lineStyle: { color: 'gradient', opacity: 0.35, curveness: 0.5 }, data: [...nodes.values()], links }],
    };
  });

  protected readonly cooccurrenceOption = computed<EChartsCoreOption | null>(() => {
    const rows = this.val(this.cooccurrence);
    if (!rows?.length) return null;
    const { ink, text, primary } = chartInk();
    const names = [...new Set(rows.flatMap((r) => [String(r['a_name']), String(r['b_name'])]))].slice(0, 24);
    const index = new Map(names.map((n, i) => [n, i]));
    const data: [number, number, number][] = [];
    for (const r of rows) {
      const a = index.get(String(r['a_name'])), b = index.get(String(r['b_name']));
      if (a == null || b == null) continue;
      data.push([a, b, Number(r['n'])], [b, a, Number(r['n'])]);
    }
    return {
      grid: { left: 130, right: 24, top: 8, bottom: 110 },
      tooltip: { formatter: (p: { value: [number, number, number] }) => `${names[p.value[0]]} × ${names[p.value[1]]}: ${p.value[2]} shared message${p.value[2] === 1 ? '' : 's'}` },
      xAxis: { type: 'category', data: names, axisLabel: { color: text, rotate: 55, width: 100, overflow: 'truncate' }, splitArea: { show: false } },
      yAxis: { type: 'category', data: names, axisLabel: { color: text, width: 120, overflow: 'truncate' } },
      visualMap: { min: 0, max: Math.max(1, ...data.map((d) => d[2])), show: false, inRange: { color: [ink + '22', primary] } },
      series: [{ type: 'heatmap', data, itemStyle: { borderColor: 'transparent', borderWidth: 2 } }],
    };
  });

  protected histogram(kind: 'confidence' | 'salience'): EChartsCoreOption | null {
    const h = this.val(this.health);
    if (!h) return null;
    const { ink, primary } = chartInk();
    const buckets = Array.from({ length: 11 }, (_, i) => i / 10);
    const counts = new Map(h[kind].map((b) => [Math.round(b.bucket * 10) / 10, b.n]));
    return {
      grid: { left: 36, right: 12, top: 8, bottom: 24 },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: buckets.map((b) => b.toFixed(1)), axisLabel: { color: ink } },
      yAxis: { type: 'value', axisLabel: { color: ink }, splitLine: { lineStyle: { color: ink, opacity: 0.15 } } },
      series: [{ type: 'bar', barWidth: '70%', itemStyle: { color: primary, borderRadius: [4, 4, 0, 0] }, data: buckets.map((b) => counts.get(b) ?? 0) }],
    };
  }

  protected readonly confidenceOption = computed(() => this.histogram('confidence'));
  protected readonly salienceOption = computed(() => this.histogram('salience'));
  protected readonly baseTypes = BASE_TYPES;
}
