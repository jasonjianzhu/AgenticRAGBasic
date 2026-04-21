# Phase 1 Database Schema

This schema supports the first phase of the product-oriented RAG system.

## Tables

- `knowledge_bases`: knowledge base records and per-KB settings.
- `documents`: uploaded document metadata, lifecycle status, file hash, and source location.
- `document_versions`: parse/build versions for each document.
- `chunks`: persisted text/table/figure chunks with retrieval metadata.
- `job_logs`: RQ job summaries for ingestion and indexing.
- `query_logs`: RAG query, rewrite, answer, latency, and trace summary.
- `app_configs`: key-value application configuration.

## Repository Layer

The first repository layer wraps SQLAlchemy session usage so API handlers,
workers, and services can share the same data access semantics.

Initial repositories:

- `KnowledgeBaseRepository`
- `DocumentRepository`
- `DocumentVersionRepository`
- `ChunkRepository`
- `JobLogRepository`
- `QueryLogRepository`

## Important Relationships

- One knowledge base has many documents.
- One document has many document versions.
- One document version has many chunks.
- Job logs can be linked to a document.
- Query logs can be linked to a knowledge base.

## Status Fields

Initial document statuses:

- `uploaded`
- `parsing`
- `chunked`
- `indexing`
- `ready`
- `failed`

Initial job statuses:

- `queued`
- `started`
- `finished`
- `failed`
- `retrying`
