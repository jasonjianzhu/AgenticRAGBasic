const toastHost = document.querySelector("#toast-host");

function showToast(message, type = "success") {
  if (!toastHost) {
    return;
  }
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toastHost.appendChild(toast);
  window.setTimeout(() => toast.remove(), 3600);
}

async function submitFormWithFetch(form) {
  const response = await fetch(form.action, {
    method: form.method || "POST",
    body: new FormData(form),
    headers: { "X-Requested-With": "fetch" },
  });
  if (!response.ok) {
    const detail = await readError(response);
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  showToast(form.dataset.successMessage || "操作已完成");
  window.location.reload();
}

async function readError(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const payload = await response.json();
    return payload.detail || payload.message || "";
  }
  return response.text();
}

function setupApiForms() {
  document.querySelectorAll("form[data-api-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await submitFormWithFetch(form);
      } catch (error) {
        showToast(error.message || "操作失败", "error");
      }
    });
  });
}

function setupRagForm() {
  const form = document.querySelector("#rag-form");
  if (!form) {
    return;
  }
  syncKnowledgeBaseId(form);
  form.querySelector("#knowledge_base_name")?.addEventListener("change", () => syncKnowledgeBaseId(form));
  form.addEventListener("submit", async (event) => {
    if (!window.fetch) {
      return;
    }
    event.preventDefault();
    const formData = new FormData(form);
    const knowledgeBaseId = String(formData.get("knowledge_base_id") || "").trim();
    const sessionId = String(formData.get("session_id") || "").trim();
    const payload = {
      query: String(formData.get("query") || ""),
      top_k: 5,
      use_reranker: formData.get("use_reranker") === "on",
    };
    if (isUuid(knowledgeBaseId)) {
      payload.knowledge_base_id = knowledgeBaseId;
    }
    if (sessionId) {
      payload.session_id = sessionId;
    }

    try {
      setLoadingState(true);
      const response = await fetch("/rag/answer", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "fetch",
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await readError(response);
        throw new Error(detail || `Request failed with ${response.status}`);
      }
      const result = await response.json();
      renderRagResult(result, formData.get("show_rewrite") === "on");
      showToast("回答已生成");
    } catch (error) {
      showToast(error.message || "RAG 请求失败", "error");
    } finally {
      setLoadingState(false);
    }
  });
}

function syncKnowledgeBaseId(form) {
  const select = form.querySelector("#knowledge_base_name");
  const hidden = form.querySelector("#knowledge_base_id");
  if (!select || !hidden) {
    return;
  }
  const option = select.options[select.selectedIndex];
  hidden.value = option?.dataset.kbId || "";
}

function setLoadingState(isLoading) {
  const button = document.querySelector("#rag-form button[type='submit']");
  if (!button) {
    return;
  }
  button.disabled = isLoading;
  button.textContent = isLoading ? "生成中..." : "提交问题";
}

function renderRagResult(result, showTrace) {
  const resultPanel = document.querySelector("#rag-client-result");
  const tracePanel = document.querySelector("#trace-panel");
  const chunkPanel = document.querySelector("#chunk-panel");
  const answer = document.querySelector("#stream-answer");
  const citations = document.querySelector("#citation-list");
  const chunks = document.querySelector("#chunk-list");
  if (!resultPanel || !answer || !citations || !chunks) {
    return;
  }

  resultPanel.classList.remove("hidden");
  chunkPanel?.classList.remove("hidden");
  streamText(answer, result.answer || "");

  citations.replaceChildren(...(result.citations || []).map(renderCitation));
  chunks.replaceChildren(...(result.chunks || []).map(renderChunk));
  renderTrace(result.trace || {}, showTrace);
  tracePanel?.classList.toggle("hidden", !showTrace);
}

function streamText(target, text) {
  target.textContent = "";
  let index = 0;
  const step = () => {
    target.textContent += text.slice(index, index + 6);
    index += 6;
    if (index < text.length) {
      window.setTimeout(step, 18);
    }
  };
  step();
}

function renderCitation(citation) {
  const card = document.createElement("div");
  card.className = "citation-card";
  card.innerHTML = `
    <strong>${escapeHtml(citation.source_filename || "unknown")}</strong>
    <span>页码 ${escapeHtml(citation.page_start || "-")}</span>
    <span>${escapeHtml(citation.section_path || "Unsectioned")}</span>
  `;
  return card;
}

function renderChunk(chunk) {
  const card = document.createElement("article");
  card.className = "chunk-card";
  card.innerHTML = `
    <div class="chunk-meta">
      <span>${escapeHtml(chunk.chunk_type || "text")}</span>
      <span>${escapeHtml(chunk.section_path || "Unsectioned")}</span>
      <span>Score ${Number(chunk.score || 0).toFixed(3)}</span>
      <span>页码 ${escapeHtml(chunk.page_start || "-")}</span>
    </div>
    <pre>${escapeHtml(chunk.content || "")}</pre>
  `;
  return card;
}

function renderTrace(trace, showTrace) {
  if (!showTrace) {
    return;
  }
  const rewrite = trace.rewrite || {};
  setText("#trace-normalized", trace.normalization?.normalized_query || "-");
  setText("#trace-rewritten", rewrite.rewritten_query || "-");
  setText("#trace-expanded", (rewrite.expanded_queries || []).join(" | ") || "-");
  setText("#trace-retrieval-queries", (rewrite.retrieval_queries || []).join(" | ") || "-");
}

function setText(selector, text) {
  const node = document.querySelector(selector);
  if (node) {
    node.textContent = text;
  }
}

function isUuid(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

setupApiForms();
setupRagForm();
