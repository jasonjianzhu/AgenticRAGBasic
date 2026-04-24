import React, { useRef, useEffect, useMemo } from 'react';
import * as echarts from 'echarts';
import type { ChartEvent } from '@/types/agent';

interface Props {
  option: ChartEvent;
}

const ChartRenderer: React.FC<Props> = React.memo(({ option }) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);

  // Stabilize option reference to avoid unnecessary re-inits
  const optionStr = useMemo(() => JSON.stringify(option), [option]);

  useEffect(() => {
    if (!chartRef.current) return;
    if (option.chart_type === 'table') return;

    // Small delay to ensure DOM is laid out
    const timer = setTimeout(() => {
      if (!chartRef.current) return;

      if (instanceRef.current) {
        instanceRef.current.dispose();
      }

      const instance = echarts.init(chartRef.current);
      instanceRef.current = instance;
      instance.setOption(option as echarts.EChartsOption, true);
    }, 50);

    return () => {
      clearTimeout(timer);
    };
  }, [optionStr]); // eslint-disable-line react-hooks/exhaustive-deps

  // Resize handler
  useEffect(() => {
    const handleResize = () => instanceRef.current?.resize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      instanceRef.current?.dispose();
      instanceRef.current = null;
    };
  }, []);

  if (option.chart_type === 'table') {
    return null;
  }

  return (
    <div
      ref={chartRef}
      style={{
        width: '100%',
        minWidth: 300,
        height: 320,
        marginBottom: 8,
        border: '1px solid #f0f0f0',
        borderRadius: 8,
        background: '#fff',
      }}
    />
  );
});

ChartRenderer.displayName = 'ChartRenderer';

export default ChartRenderer;
