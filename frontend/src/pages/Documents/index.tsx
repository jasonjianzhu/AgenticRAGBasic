import React, { useEffect, useState, useCallback } from 'react';
import {
  Table,
  Button,
  Select,
  Upload,
  Tag,
  Space,
  Popconfirm,
  Modal,
  message,
  Typography,
  Spin,
} from 'antd';
import {
  UploadOutlined,
  InboxOutlined,
  ReloadOutlined,
  DeleteOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  StopOutlined,
  RedoOutlined,
} from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import type { ColumnsType } from 'antd/es/table';
import type { UploadFile } from 'antd/es/upload';
import * as api from '@/api/client';
import type {
  KBResponse,
  DocumentResponse,
  ChunkResponse,
} from '@/types';

const { Dragger } = Upload;
const { Text, Paragraph } = Typography;

const statusColorMap: Record<string, string> = {
  uploaded: 'blue',
  parsing: 'orange',
  chunked: 'cyan',
  indexing: 'purple',
  ready: 'green',
  failed: 'red',
  disabled: 'default',
};

const statusLabelMap: Record<string, string> = {
  uploaded: '已上传',
  parsing: '解析中',
  chunked: '已切块',
  indexing: '索引中',
  ready: '就绪',
  failed: '失败',
  disabled: '已禁用',
};

const docTypeOptions = [
  { label: '全部', value: '' },
  { label: '手册 (manual)', value: 'manual' },
  { label: 'FAQ', value: 'faq' },
  { label: 'QA', value: 'qa' },
  { label: '规格书 (spec)', value: 'spec' },
  { label: '未知', value: 'unknown' },
];

const profileOptions = [
  { label: '使用默认', value: '' },
  { label: 'Fast', value: 'fast' },
  { label: 'Balanced', value: 'balanced' },
  { label: 'Accurate', value: 'accurate' },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const DocumentsPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const initialKB = searchParams.get('kb') || undefined;

  const [loading, setLoading] = useState(false);
  const [docs, setDocs] = useState<DocumentResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  // KB list for selector
  const [kbs, setKbs] = useState<KBResponse[]>([]);
  const [selectedKB, setSelectedKB] = useState<string | undefined>(initialKB);

  // Upload state
  const [uploadKB, setUploadKB] = useState<string | undefined>(initialKB);
  const [uploadDocType, setUploadDocType] = useState('');
  const [uploadProfile, setUploadProfile] = useState('');
  const [uploading, setUploading] = useState(false);

  // Chunk preview
  const [chunkModalOpen, setChunkModalOpen] = useState(false);
  const [chunkLoading, setChunkLoading] = useState(false);
  const [chunks, setChunks] = useState<ChunkResponse[]>([]);
  const [chunkTotal, setChunkTotal] = useState(0);
  const [chunkDocTitle, setChunkDocTitle] = useState('');

  const fetchKBs = useCallback(async () => {
    try {
      const data = await api.listKBs();
      setKbs(data.items);
    } catch {
      // silent
    }
  }, []);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listDocuments({
        knowledge_base_id: selectedKB || undefined,
        skip: (page - 1) * pageSize,
        limit: pageSize,
      });
      setDocs(data.items);
      setTotal(data.total);
    } catch {
      message.error('获取文档列表失败');
    } finally {
      setLoading(false);
    }
  }, [selectedKB, page]);

  useEffect(() => {
    fetchKBs();
  }, [fetchKBs]);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  const handleUpload = async (file: File) => {
    if (!uploadKB) {
      message.warning('请先选择知识库');
      return;
    }
    setUploading(true);
    try {
      await api.uploadDocument(
        file,
        uploadKB,
        uploadDocType || undefined,
        uploadProfile || undefined,
      );
      message.success('文档上传成功');
      fetchDocs();
    } catch (err: unknown) {
      const msg =
        err && typeof err === 'object' && 'response' in err
          ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? '上传失败')
          : '上传失败';
      message.error(msg);
    } finally {
      setUploading(false);
    }
  };

  const handleToggle = async (doc: DocumentResponse) => {
    try {
      if (doc.is_enabled) {
        await api.disableDocument(doc.id);
        message.success('文档已禁用');
      } else {
        await api.enableDocument(doc.id);
        message.success('文档已启用');
      }
      fetchDocs();
    } catch {
      message.error('操作失败');
    }
  };

  const handleDelete = async (docId: string) => {
    try {
      await api.deleteDocument(docId);
      message.success('文档已删除');
      fetchDocs();
    } catch {
      message.error('删除失败');
    }
  };

  const handleRetry = async (doc: DocumentResponse) => {
    if (!doc.job_id) {
      message.warning('无关联任务');
      return;
    }
    try {
      await api.retryJob(doc.job_id);
      message.success('重试任务已提交');
      fetchDocs();
    } catch {
      message.error('重试失败');
    }
  };

  const openChunks = async (doc: DocumentResponse) => {
    setChunkDocTitle(doc.title);
    setChunkModalOpen(true);
    setChunkLoading(true);
    try {
      const data = await api.getDocumentChunks(doc.id, 0, 100);
      setChunks(data.items);
      setChunkTotal(data.total);
    } catch {
      message.error('获取 Chunk 列表失败');
    } finally {
      setChunkLoading(false);
    }
  };

  const kbNameMap = Object.fromEntries(kbs.map((kb) => [kb.id, kb.name]));

  const columns: ColumnsType<DocumentResponse> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
    },
    {
      title: '知识库',
      dataIndex: 'knowledge_base_id',
      key: 'kb',
      width: 160,
      render: (id: string) => kbNameMap[id] || id.slice(0, 8),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => (
        <Tag color={statusColorMap[s] || 'default'}>
          {statusLabelMap[s] || s}
        </Tag>
      ),
    },
    {
      title: '文档类型',
      dataIndex: 'document_type',
      key: 'document_type',
      width: 100,
    },
    {
      title: '大小',
      dataIndex: 'file_size_bytes',
      key: 'size',
      width: 100,
      render: (v: number) => formatBytes(v),
    },
    {
      title: '启用',
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      width: 60,
      render: (v: boolean) =>
        v ? <Tag color="green">是</Tag> : <Tag color="default">否</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => new Date(t).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 280,
      render: (_: unknown, record: DocumentResponse) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={record.is_enabled ? <StopOutlined /> : <CheckCircleOutlined />}
            onClick={() => handleToggle(record)}
          >
            {record.is_enabled ? '禁用' : '启用'}
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => openChunks(record)}
          >
            Chunks
          </Button>
          {record.status === 'failed' && (
            <Button
              type="link"
              size="small"
              icon={<RedoOutlined />}
              onClick={() => handleRetry(record)}
            >
              重试
            </Button>
          )}
          <Popconfirm
            title="确定删除该文档？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const chunkColumns: ColumnsType<ChunkResponse> = [
    { title: '#', dataIndex: 'ordinal', key: 'ordinal', width: 50 },
    { title: '类型', dataIndex: 'chunk_type', key: 'chunk_type', width: 100 },
    {
      title: '内容',
      dataIndex: 'content',
      key: 'content',
      render: (text: string) => (
        <Paragraph
          ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
          style={{ marginBottom: 0, fontSize: 13 }}
        >
          {text}
        </Paragraph>
      ),
    },
    {
      title: '章节路径',
      dataIndex: 'section_path',
      key: 'section_path',
      width: 180,
      ellipsis: true,
      render: (v: string | null) => v || '-',
    },
    {
      title: '页码',
      key: 'pages',
      width: 80,
      render: (_: unknown, r: ChunkResponse) =>
        r.page_start != null
          ? r.page_start === r.page_end
            ? `P${r.page_start}`
            : `P${r.page_start}-${r.page_end}`
          : '-',
    },
    {
      title: 'Tokens',
      dataIndex: 'token_count',
      key: 'token_count',
      width: 70,
      render: (v: number | null) => v ?? '-',
    },
  ];

  return (
    <div>
      {/* Upload area */}
      <div style={{ marginBottom: 24 }}>
        <Space style={{ marginBottom: 12 }} wrap>
          <Text strong>上传到知识库：</Text>
          <Select
            style={{ width: 240 }}
            placeholder="选择知识库"
            value={uploadKB}
            onChange={setUploadKB}
            options={kbs.map((kb) => ({ label: kb.name, value: kb.id }))}
            allowClear
          />
          <Select
            style={{ width: 140 }}
            placeholder="文档类型"
            value={uploadDocType}
            onChange={setUploadDocType}
            options={docTypeOptions.filter((o) => o.value !== '')}
            allowClear
          />
          <Select
            style={{ width: 140 }}
            placeholder="解析 Profile"
            value={uploadProfile}
            onChange={setUploadProfile}
            options={profileOptions.filter((o) => o.value !== '')}
            allowClear
          />
        </Space>
        <Dragger
          accept=".pdf"
          multiple={false}
          showUploadList={false}
          customRequest={({ file }) => {
            handleUpload(file as File);
          }}
          disabled={uploading || !uploadKB}
          style={{ maxWidth: 600 }}
        >
          <p className="ant-upload-drag-icon">
            {uploading ? <Spin /> : <InboxOutlined />}
          </p>
          <p className="ant-upload-text">点击或拖拽 PDF 文件到此区域上传</p>
          <p className="ant-upload-hint">仅支持 PDF 格式，最大 50MB</p>
        </Dragger>
      </div>

      {/* Filter bar */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Text>筛选知识库：</Text>
          <Select
            style={{ width: 240 }}
            placeholder="全部知识库"
            value={selectedKB}
            onChange={(v) => {
              setSelectedKB(v);
              setPage(1);
            }}
            options={[
              { label: '全部', value: undefined as unknown as string },
              ...kbs.map((kb) => ({ label: kb.name, value: kb.id })),
            ]}
            allowClear
          />
        </Space>
        <Button icon={<ReloadOutlined />} onClick={fetchDocs}>
          刷新
        </Button>
      </div>

      {/* Documents table */}
      <Table
        rowKey="id"
        columns={columns}
        dataSource={docs}
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize,
          showSizeChanger: false,
          onChange: setPage,
        }}
        scroll={{ x: 1100 }}
      />

      {/* Chunk preview modal */}
      <Modal
        title={`Chunk 预览 - ${chunkDocTitle}`}
        open={chunkModalOpen}
        onCancel={() => setChunkModalOpen(false)}
        footer={null}
        width={900}
        destroyOnClose
      >
        <Table
          rowKey="id"
          columns={chunkColumns}
          dataSource={chunks}
          loading={chunkLoading}
          pagination={{ pageSize: 10, total: chunkTotal, showSizeChanger: false }}
          size="small"
          scroll={{ x: 800 }}
        />
      </Modal>
    </div>
  );
};

export default DocumentsPage;
