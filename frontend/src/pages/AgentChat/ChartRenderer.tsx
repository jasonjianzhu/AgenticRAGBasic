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

    // If it's a "table" type chart, skip ECharts rendering
    if (option.chart_type === 'table') return;

    if (!instanceRef.current) {
      instanceRef.current = echarts.init(chartRef.current);
    }

    // The option from backend is already ECharts-compatible
    instanceRef.current.setOption(option as echarts.EChartsOption, true);

    const handleResize = () => instanceRef.current?.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [option]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      instanceRef.current?.dispose();
    };
  }, []);

  if (option.chart_type === 'table') {
    return null; // Table type is handled by DataTable component
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
