import React, { useEffect, useState, useCallback } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Card,
  Statistic,
  Space,
  Tag,
  Popconfirm,
  message,
  Row,
  Col,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  EditOutlined,
  DeleteOutlined,
  BuildOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  BlockOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { ColumnsType } from 'antd/es/table';
import * as api from '@/api/client';
import type { KBResponse, KBDetailResponse } from '@/types';

const chunkerOptions = [
  { label: 'Docling Hybrid', value: 'docling_hybrid' },
  { label: 'Markdown Header', value: 'markdown_header' },
  { label: 'Recursive Token', value: 'recursive_token' },
];

const profileOptions = [
  { label: 'Fast', value: 'fast' },
  { label: 'Balanced', value: 'balanced' },
  { label: 'Accurate', value: 'accurate' },
];

const KnowledgeBasePage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [kbs, setKbs] = useState<KBResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingKB, setEditingKB] = useState<KBResponse | null>(null);
  const [form] = Form.useForm();

  // Aggregate statistics
  const [stats, setStats] = useState({ totalKBs: 0, totalDocs: 0, totalChunks: 0 });

  const fetchKBs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listKBs();
      setKbs(data.items);
      setTotal(data.total);

      // Fetch detail for each KB to get statistics
      let totalDocs = 0;
      let totalChunks = 0;
      const details = await Promise.allSettled(
        data.items.map((kb) => api.getKB(kb.id)),
      );
      for (const d of details) {
        if (d.status === 'fulfilled') {
          const detail = d.value as KBDetailResponse;
          totalDocs += detail.statistics?.document_count ?? 0;
          totalChunks += detail.statistics?.chunk_count ?? 0;
        }
      }
      setStats({ totalKBs: data.total, totalDocs, totalChunks });
    } catch (err: unknown) {
      message.error('获取知识库列表失败');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKBs();
  }, [fetchKBs]);

  const openCreate = () => {
    setEditingKB(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (kb: KBResponse) => {
    setEditingKB(kb);
    form.setFieldsValue({
      name: kb.name,
      description: kb.description,
      default_chunker: (kb.settings as Record<string, string>)?.default_chunker ?? 'docling_hybrid',
      default_parser_profile: (kb.settings as Record<string, string>)?.default_parser_profile ?? 'balanced',
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        name: values.name,
        description: values.description || undefined,
        settings: {
          default_chunker: values.default_chunker || 'docling_hybrid',
          default_parser_profile: values.default_parser_profile || 'balanced',
        },
      };
      if (editingKB) {
        await api.updateKB(editingKB.id, payload);
        message.success('知识库已更新');
      } else {
        await api.createKB(payload);
        message.success('知识库已创建');
      }
      setModalOpen(false);
      fetchKBs();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) return; // form validation
      message.error('操作失败');
      console.error(err);
    }
  };

  const handleDelete = async (kbId: string) => {
    try {
      await api.deleteKB(kbId);
      message.success('知识库已删除');
      fetchKBs();
    } catch {
      message.error('删除失败');
    }
  };

  const handleBuild = async (kbId: string) => {
    try {
      await api.buildIndex(kbId);
      message.success('索引构建任务已提交');
    } catch {
      message.error('索引构建失败');
    }
  };

  const columns: ColumnsType<KBResponse> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: KBResponse) => (
        <a onClick={() => navigate(`/documents?kb=${record.id}`)}>{text}</a>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (text: string | null) => text || '-',
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (active: boolean) =>
        active ? <Tag color="green">启用</Tag> : <Tag color="default">停用</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (t: string) => new Date(t).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 240,
      render: (_: unknown, record: KBResponse) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            icon={<BuildOutlined />}
            onClick={() => handleBuild(record.id)}
          >
            构建索引
          </Button>
          <Popconfirm
            title="确定删除该知识库？"
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

  return (
    <div>
      {/* Statistics cards */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic
              title="知识库总数"
              value={stats.totalKBs}
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="文档总数"
              value={stats.totalDocs}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="Chunk 总数"
              value={stats.totalChunks}
              prefix={<BlockOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Toolbar */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          创建知识库
        </Button>
        <Button icon={<ReloadOutlined />} onClick={fetchKBs}>
          刷新
        </Button>
      </div>

      {/* Table */}
      <Table
        rowKey="id"
        columns={columns}
        dataSource={kbs}
        loading={loading}
        pagination={{ total, pageSize: 20, showSizeChanger: false }}
      />

      {/* Create / Edit Modal */}
      <Modal
        title={editingKB ? '编辑知识库' : '创建知识库'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        okText="确定"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入知识库名称' }]}
          >
            <Input placeholder="例如：储能产品知识库" maxLength={200} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="知识库描述（可选）" />
          </Form.Item>
          <Form.Item name="default_chunker" label="Chunker 策略" initialValue="docling_hybrid">
            <Select options={chunkerOptions} />
          </Form.Item>
          <Form.Item name="default_parser_profile" label="解析 Profile" initialValue="balanced">
            <Select options={profileOptions} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default KnowledgeBasePage;
