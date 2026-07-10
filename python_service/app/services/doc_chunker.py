"""DocChunker — RAG 文档分块 (Phase 5 补全, ★ 剩余优化项).

开发指南 §6 Phase5:
  "文档 chunk + 向量化 (LanceDB)"
  现有 vector/lancedb_store.py 的 upsert_documents(rows) 接收已 chunk 的 rows,
  本模块补全 chunk 预处理.

分块策略:
  1. 按段落 (双换行) 优先分割
  2. 段落超 max_chars → 按滑动窗口切分 + overlap
  3. 段落小 → 合并到 max_chars (减少碎片)

token 估算: 中文 1 字符 ≈ 1 token, 英文 4 字符 ≈ 1 token, 混合取 max_chars 近似.
返回 rows 格式兼容 lancedb upsert_documents: [{text, symbol, chunk_idx, metadata}].

用法:
  chunker = DocChunker()
  rows = chunker.chunk(long_text, symbol="AAPL", source="research.pdf")
  store.upsert_documents(rows)  # 落 LanceDB
"""

from __future__ import annotations

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 1500     # ≈ 500 tokens (混合中英)
DEFAULT_OVERLAP_CHARS = 300  # ≈ 100 tokens overlap


class DocChunker:
    """RAG 文档分块器.

    用法:
      chunker = DocChunker(max_chars=1500, overlap=300)
      rows = chunker.chunk(text, symbol="AAPL", source="report.md")
      lancedb_store.upsert_documents(rows)
    """

    def __init__(self, max_chars: int = DEFAULT_MAX_CHARS,
                 overlap: int = DEFAULT_OVERLAP_CHARS):
        self.max_chars = max(50, max_chars)  # 最小 50 防止荒谬值
        self.overlap = max(0, min(overlap, self.max_chars // 2))

    def chunk(self, text: str, *, symbol: str = "", source: str = "",
              doc_type: str = "research", extra: Optional[dict] = None) -> list[dict]:
        """文档分块 → rows (兼容 lancedb upsert_documents).

        Returns:
            list[{text, symbol, chunk_idx, source, doc_type, char_count, ...extra}]
        """
        if not text or not text.strip():
            return []

        # 1. 按段落分割
        paragraphs = self._split_paragraphs(text)
        # 2. 合并小段落 + 切分大段落
        chunks = self._merge_and_split(paragraphs)
        # 3. 组装 rows
        rows = []
        for idx, chk in enumerate(chunks):
            row = {
                "text": chk,
                "symbol": symbol,
                "chunk_idx": idx,
                "source": source,
                "doc_type": doc_type,
                "char_count": len(chk),
            }
            if extra:
                row.update(extra)
            rows.append(row)
        logger.debug("[DocChunker] %s → %d chunks (max=%d, overlap=%d)",
                     source or "(text)", len(rows), self.max_chars, self.overlap)
        return rows

    def chunk_many(self, docs: list[dict]) -> list[dict]:
        """批量分块. docs: [{text, symbol, source, ...}]"""
        all_rows = []
        for d in docs:
            text = d.pop("text", "")
            rows = self.chunk(text, **d)
            all_rows.extend(rows)
        return all_rows

    # ── 内部 ──────────────────────────────────────────────────────────

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        """按双换行/单换行+空行 分段, 保留段落内单换行."""
        # 标准化: \r\n → \n
        t = text.replace("\r\n", "\n").replace("\r", "\n")
        # 按两个以上换行分段
        paras = re.split(r"\n\s*\n", t)
        return [p.strip() for p in paras if p.strip()]

    def _merge_and_split(self, paragraphs: list[str]) -> list[str]:
        """合并小段落 + 切分大段落."""
        chunks: list[str] = []
        buf = ""

        for para in paragraphs:
            # 大段落 → 直接切分
            if len(para) > self.max_chars:
                # 先 flush buf
                if buf:
                    chunks.append(buf.strip())
                    buf = ""
                chunks.extend(self._sliding_window(para))
                continue
            # 小段落 → 尝试合并到 buf
            if len(buf) + len(para) + 2 <= self.max_chars:
                buf = (buf + "\n\n" + para) if buf else para
            else:
                if buf:
                    chunks.append(buf.strip())
                buf = para
        if buf:
            chunks.append(buf.strip())
        return [c for c in chunks if c]

    def _sliding_window(self, text: str) -> list[str]:
        """滑动窗口切分超长文本 (带 overlap)."""
        chunks = []
        start = 0
        n = len(text)
        step = self.max_chars - self.overlap
        while start < n:
            end = min(start + self.max_chars, n)
            chunks.append(text[start:end].strip())
            if end >= n:
                break
            start += step
            # 避免在词中间断开 (优先在空格/标点处)
            if start < n:
                # 回退到最近的空格/标点
                for offset in range(min(50, start)):
                    if text[start - offset] in " \t，。；,.;\n":
                        start = start - offset + 1
                        break
        return [c for c in chunks if c]


# 进程级默认实例
doc_chunker = DocChunker()
