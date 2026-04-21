import React, { useEffect, useState, useCallback } from 'react';
import {
  Select,
  Input,
  Button,
  Slider,
  Card,
  Tag,
  Space,
  Descriptions,
  Empty,
  Spin,
  Typography,
  message,
  Row,
  Col,
  Statistic,
  Collapse,
} from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import * as api from '@/api/client';
import type {
  KBResponse,
  SearchResultItem,
  SearchTrace,
  SearchDebugResponse,
} from '@/types';

const { Text, Paragraph } = Typography;

function highlightText(content: string, query: string): React.ReactNode {
  if (!query.trim()) return content;
  // Split query into individual terms for highlighting
  const terms = query
    .trim()
    .split(/\s+/)
    .filter((t) => t.length > 0);
  if (terms.length === 0) return content;

  const pattern = new RegExp(`(${terms.map(escapeRegex).join('|')})`, 'gi');
  const parts = content.split(pattern);
  return parts.map((part, i) =>
    pattern.test(part) ? <mark key={i}>{part}</mark> : part,
  );
}

function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const SearchDebugPage: React.FC = () => {
  const [kbs, setKbs] = useState<KBResponse[]>([]);
  const [selectedKB, setSelectedKB] = useState<string>();
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(10);

  // Filters
  const [docType, setDocType] = useState<string>();
  const [language, setLanguage] = useState<string>();
  const [productModel, setProductModel] = useState('');

  // Results
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [trace, setTrace] = useState<SearchTrace | null>(null);
  const [searchedQuery, setSearchedQuery] = useState('');

  const fetchKBs = useCallback(async () => {
    try {
      const data = await api.listKBs();
      setKbs(data.items);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    fetchKBs();
  }, [fetchKBs]);

  const handleSearch = async () => {
    if (!selectedKB) {
      message.warning('请选择知识库');
      return;
    }
    if (!query.trim()) {
      message.warning('请输入检索内容');
      return;
    }

    setSearching(true);
    setResults([]);
    setTrace(null);
    try {
      const filters: Record<string, string> = {};
      if (docType) filters.document_type = docType;
      if (language) filters.language = language;
      if (productModel.trim()) filters.product_model = productModel.trim();

      const data: SearchDebugResponse = await api.searchDebug(selectedKB, {
        query: query.trim(),
        top_k: topK,
        filters: Object.keys(filters).length > 0 ? filters : undefined,
      });
      setResults(data.results);
      setTrace(data.trace);
      setSearchedQuery(data.query);
    } catch (err: unknown) {
      const msg =
        err && typeof err === 'object' && 'response' in err
          ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? '检索失败')
          : '检索失败';
      message.error(msg);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div>
      {/* Search controls */}
      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {/* KB selector + query */}
          <Row gutter={12}>
            <Col span={6}>
              <Select
                style={{ width: '100%' }}
                placeholder="选择知识库"
                value={selectedKB}
                onChange={setSelectedKB}
                options={kbs.map((kb) => ({ label: kb.name, value: kb.id }))}
                allowClear
              />
            </Col>
            <Col span={14}>
              <Input
                placeholder="输入检索内容，例如：电池过温告警处理"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onPressEnter={handleSearch}
              />
            </Col>
            <Col span={4}>
              <Button
                type="primary"
                icon={<SearchOutlined />}
                onClick={handleSearch}
                loading={searching}
                block
              >
                检索
              </Button>
            </Col>
          </Row>

          {/* Filters */}
          <Row gutter={12} align="middle">
            <Col>
              <Text type="secondary">过滤条件：</Text>
            </Col>
            <Col>
              <Select
                style={{ width: 140 }}
                placeholder="文档类型"
                value={docType}
                onChange={setDocType}
                allowClear
                options={[
                  { label: 'manual', value: 'manual' },
                  { label: 'faq', value: 'faq' },
                  { label: 'qa', value: 'qa' },
                  { label: 'spec', value: 'spec' },
                ]}
              />
            </Col>
            <Col>
              <Select
                style={{ width: 100 }}
                placeholder="语言"
                value={language}
                onChange={setLanguage}
                allowClear
                options={[
                  { label: '中文', value: 'zh' },
                  { label: 'English', value: 'en' },
                ]}
              />
            </Col>
            <Col>
              <Input
                style={{ width: 160 }}
                placeholder="产品型号"
                value={productModel}
                onChange={(e) => setProductModel(e.target.value)}
                allowClear
              />
            </Col>
            <Col flex="auto">
              <Space>
                <Text type="secondary">Top-K: {topK}</Text>
                <Slider
                  style={{ width: 200 }}
                  min={1}
                  max={50}
                  value={topK}
                  onChange={setTopK}
                />
              </Space>
            </Col>
          </Row>
        </Space>
      </Card>

      {/* Trace panel */}
      {trace && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Row gutter={24}>
            <Col>
              <Statistic title="Dense 命中" value={trace.dense_hits} />
            </Col>
            <Col>
              <Statistic title="Sparse 命中" value={trace.sparse_hits} />
            </Col>
            <Col>
              <Statistic title="融合总数" value={trace.fused_total} />
            </Col>
            <Col>
              <Statistic title="返回数" value={trace.returned} />
            </Col>
          </Row>
        </Card>
      )}

      {/* Results */}
      {searching && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" />
        </div>
      )}

      {!searching && results.length === 0 && trace && (
        <Empty description="无检索结果" />
      )}

      {!searching &&
        results.map((item, idx) => (
          <Card
            key={item.chunk_id}
            size="small"
            className="search-result-card"
            title={
              <Space>
                <Tag color="blue">#{idx + 1}</Tag>
                <Text strong className="score-badge" style={{ color: '#1677ff' }}>
                  {item.score.toFixed(4)}
                </Text>
                <Text type="secondary">{item.document_title}</Text>
              </Space>
            }
          >
            <div className="chunk-content" style={{ marginBottom: 12 }}>
              {highlightText(item.content, searchedQuery)}
            </div>
            <Descriptions size="small" column={4}>
              <Descriptions.Item label="类型">
                <Tag>{item.chunk_type}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="章节路径">
                {item.section_path || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="页码">
                {item.page_start != null
                  ? item.page_start === item.page_end
                    ? `P${item.page_start}`
                    : `P${item.page_start}-${item.page_end}`
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="文档 ID">
                <Text copyable={{ text: item.document_id }} style={{ fontSize: 12 }}>
                  {item.document_id.slice(0, 8)}...
                </Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        ))}
    </div>
  );
};

export default SearchDebugPage;
