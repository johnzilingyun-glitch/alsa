import sys
sys.path.insert(0, "python_service")
from app.services.doc_chunker import DocChunker
c = DocChunker(max_chars=100, overlap=20)
rows = c.chunk("长文本内容。" * 50, symbol="X")
print("chunks:", len(rows))
for r in rows:
    print("  idx", r["chunk_idx"], "chars", r["char_count"], "max100")
print("max char_count:", max(r["char_count"] for r in rows))
