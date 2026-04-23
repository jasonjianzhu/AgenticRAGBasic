import React from 'react';
import { Table, Typography } from 'antd';
import type { DataTableEvent } from '@/types/agent';

const { Text } = Typography;

interface Props {
  data: DataTableEvent;
}

const DataTable: React.FC<Props> = ({ data }) => {
  const columns = data.columns.map((col, idx) => ({
    title: col,
    dataIndex: `col_${idx}`,
    key: `col_${idx}`,
    ellipsis: true,
  }));

  const dataSource = data.rows.map((row, rowIdx) => {
    const record: Record<string, unknown> = { key: rowIdx };
    row.forEach((val, colIdx) => {
      record[`col_${colIdx}`] = val;
    });
    return record;
  });

  return (
    <div style={{ marginBottom: 8 }}>
      <Text type="secondary" style={{ fontSize: 11, marginBottom: 4, display: 'block' }}>
        查询结果（{data.row_count} 行）
      </Text>
      <Table
        columns={columns}
        dataSource={dataSource}
        size="small"
        pagination={data.rows.length > 10 ? { pageSize: 10, size: 'small' } : false}
        scroll={{ x: 'max-content' }}
        bordered
        style={{ fontSize: 12 }}
      />
    </div>
  );
};

export default DataTable;
