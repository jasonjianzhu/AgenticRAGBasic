import React, { useRef, useEffect, useMemo } from 'react';
import * as echarts from 'echarts';
import type { ChartEvent } from '@/types/agent';

interface Props {
  option: ChartEvent;
}

const ChartRenderer: React.FC<Props> = React.memo(({ option }) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);
  const observerRef = useRef<ResizeObserver | null>(null);

  const optionStr = useMemo(() => JSON.stringify(option), [option]);

  useEffect(() => {
    const el = chartRef.current;
    if (!el || option.chart_type === 'table') return;

    // Wait for container to have dimensions
    const initChart = () => {
      if (!el.clientWidth) return;

      if (instanceRef.current) {
        instanceRef.current.dispose();
      }

      const instance = echarts.init(el);
      instanceRef.current = instance;
      instance.setOption(option as echarts.EChartsOption, true);
    };

    // Use ResizeObserver to detect when container gets dimensions
    observerRef.current = new ResizeObserver(() => {
      if (el.clientWidth > 0) {
        if (!instanceRef.current) {
          initChart();
        } else {
          instanceRef.current.resize();
        }
      }
    });
    observerRef.current.observe(el);

    // Also try immediate init
    requestAnimationFrame(initChart);

    return () => {
      observerRef.current?.disconnect();
      instanceRef.current?.dispose();
      instanceRef.current = null;
    };
  }, [optionStr]); // eslint-disable-line react-hooks/exhaustive-deps

  if (option.chart_type === 'table') return null;

  return (
    <div
      ref={chartRef}
      style={{
        width: 500,
        maxWidth: '100%',
        height: 320,
        marginBottom: 8,
        borderRadius: 8,
        background: '#fff',
      }}
    />
  );
});

ChartRenderer.displayName = 'ChartRenderer';

export default ChartRenderer;
