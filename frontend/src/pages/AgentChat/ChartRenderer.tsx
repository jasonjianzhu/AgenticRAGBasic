import React, { useRef, useEffect } from 'react';
import * as echarts from 'echarts';
import type { ChartEvent } from '@/types/agent';

interface Props {
  option: ChartEvent;
}

const ChartRenderer: React.FC<Props> = ({ option }) => {
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!chartRef.current) return;
    if (option.chart_type === 'table') return;

    const el = chartRef.current;

    // Init with delay to ensure DOM is ready
    const timer = setTimeout(() => {
      // Dispose any existing instance on this element
      const existing = echarts.getInstanceByDom(el);
      if (existing) existing.dispose();

      const instance = echarts.init(el);
      instance.setOption(option as echarts.EChartsOption);

      // Handle window resize
      const onResize = () => instance.resize();
      window.addEventListener('resize', onResize);

      // Cleanup stored for this effect
      (el as any).__echarts_cleanup = () => {
        window.removeEventListener('resize', onResize);
        instance.dispose();
      };
    }, 100);

    return () => {
      clearTimeout(timer);
      if ((el as any).__echarts_cleanup) {
        (el as any).__echarts_cleanup();
        delete (el as any).__echarts_cleanup;
      }
    };
  }, [JSON.stringify(option)]);

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
        background: '#fafafa',
        border: '1px solid #f0f0f0',
      }}
    />
  );
};

export default ChartRenderer;
