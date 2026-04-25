/**
 * 清理 LLM 输出内容的工具函数。
 * 统一处理 <think> 标签等，避免在多个组件里重复正则。
 */

/** 移除 <think>...</think> 块（含未闭合的） */
export function stripThinkTags(text: string): string {
  let cleaned = text.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
  if (cleaned.includes('<think>')) {
    cleaned = cleaned.replace(/<think>[\s\S]*/g, '').trim();
  }
  return cleaned;
}
