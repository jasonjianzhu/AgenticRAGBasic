import React, { useRef, useEffect } from 'react';
import * as echarts from 'echarts';
import type { ChartEvent } from '@/types/agent';

interface Props {
  option: ChartEvent;
}

const ChartRenderer: React.FC<Props> = ({ option }) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current) return;
    if (option.chart_type === 'table') return;

    // Dispose old instance if exists (handles re-renders)
    if (instanceRef.current) {
      instanceRef.current.dispose();
    }

    const instance = echarts.init(chartRef.current);
    instanceRef.current = instance;

    instance.setOption(option as echarts.EChartsOption, true);

    // Delay resize to ensure container has correct dimensions
    const timer = setTimeout(() => instance.resize(), 100);

    const handleResize = () => instance.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', handleResize);
      instance.dispose();
      instanceRef.current = null;
    };
  }, [option]);

  if (option.chart_type === 'table') {
    return null;
  }

  return (
    <div
      ref={chartRef}
      style={{
        width: '100%',
        height: 320,
        marginBottom: 8,
        border: '1px solid #f0f0f0',
        borderRadius: 8,
        background: '#fff',
      }}
    />
  );
};

export default ChartRenderer;
