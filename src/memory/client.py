
import sqlite3
import warnings
import os
from datetime import datetime
from typing import Optional

from src.config import get_settings


def _init_db(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        user_id TEXT NOT NULL DEFAULT 'user1',
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        content TEXT NOT NULL,
        user_id TEXT NOT NULL DEFAULT 'user1',
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );
    CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        segment_text TEXT NOT NULL,
        summary TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );
    """)
    # 迁移：旧表可能缺列
    for table, col in [("notes", "user_id"), ("conversations", "user_id"),
                       ("notes", "updated_at")]:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass  # 列已存在
    conn.commit()


class MemoryClient:
    def __init__(self):
        s = get_settings()
        self.sqlite_path = s["sqlite_path"]
        if self.sqlite_path != ":memory:":
            os.makedirs(os.path.dirname(self.sqlite_path), exist_ok=True)
            self.conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
            _init_db(self.conn)
        else:
            self.conn = sqlite3.connect(":memory:", check_same_thread=False)
            _init_db(self.conn)

        self.qdrant = None
        self._try_connect_qdrant()
        # Neo4j 由 graph.py 的 _get_driver() 统一管理，client 不再持有独立连接

    # ── 内部连接 ──────────────────────────────────────────────
    def _try_connect_qdrant(self):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import VectorParams, Distance
            s = get_settings()
            self.qdrant = QdrantClient(host=s["qdrant_host"], port=s["qdrant_port"])
            self.qdrant.get_collections()
            # 初始化 collection
            collection_name = "companion_memory"
            try:
                self.qdrant.get_collection(collection_name)
            except Exception:
                self.qdrant.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=1024, distance=Distance.COSINE))
            self._qdrant_collection = collection_name
        except Exception as e:
            self.qdrant = None
            self._qdrant_collection = None
            warnings.warn(f"[warn] Qdrant 未就绪，向量检索降级关闭：{e}")

    # ── 对话 ────────────────────────────────────────────────
    def _upsert_vector(self, doc_id: int, text: str, payload: dict):
        """将文本向量化后存入 Qdrant。失败静默降级。"""
        if self.qdrant is None:
            return
        try:
            from src.memory.embedding import embed_texts
            vectors = embed_texts([text])
            if vectors is None:
                return
            from qdrant_client.models import PointStruct
            self.qdrant.upsert(
                collection_name=self._qdrant_collection,
                points=[PointStruct(id=doc_id, vector=vectors[0], payload=payload)]
            )
        except Exception as e:
            warnings.warn(f"[warn] 向量写入失败（已降级）：{e}")

    def save_dialogue(self, role: str, content: str, source_user_id: str = "user1"):
        cur = self.conn.execute(
            "INSERT INTO conversations (role, content, user_id) VALUES (?, ?, ?)",
            (role, content, source_user_id))
        self.conn.commit()
        # 向量化存储
        if role == "user":  # 只存用户消息，避免冗余
            self._upsert_vector(
                doc_id=cur.lastrowid,
                text=content,
                payload={"type": "dialogue", "role": role, "content": content,
                         "user_id": source_user_id}
            )
        self._maybe_summarize()

    def _maybe_summarize(self):
        """每 10 条对话自动生成语义摘要段落。"""
        count = self.conn.execute(
            "SELECT COUNT(*) FROM conversations").fetchone()[0]
        if count == 0 or count % 10 != 0:
            return
        existing = self.conn.execute(
            "SELECT COUNT(*) FROM summaries").fetchone()[0]
        if existing >= count // 10:
            return
        rows = self.conn.execute(
            "SELECT role, content FROM conversations "
            "ORDER BY id DESC LIMIT 10").fetchall()
        segment = " | ".join(f"{r}:{c}" for r, c in reversed(rows))
        try:
            summary = self._generate_summary(segment)
        except Exception:
            summary = segment[:200]  # LLM 失败时降级为原文截断
        self.save_summary(segment, summary)

    def _generate_summary(self, segment: str) -> str:
        """使用 LLM 生成语义摘要，失败时降级为原文截断。"""
        try:
            from langchain_core.messages import HumanMessage
            from src.llm_factory import get_llm
            from src.memory.prompts import SUMMARY_PROMPT
            llm = get_llm(temperature=0.3, timeout=10)
            resp = llm.invoke([HumanMessage(content=SUMMARY_PROMPT.format(segment=segment))])
            return resp.content[:500] if resp.content else segment[:200]
        except Exception:
            # 降级：LLM 不可用时用原文截断
            return segment[:200]

    def search_dialogue(self, keyword: str, limit: int = 5) -> list:
        cur = self.conn.execute(
            "SELECT role, content, created_at FROM conversations "
            "WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{keyword}%", limit))
        return [{"role": r[0], "content": r[1], "created_at": r[2]}
                for r in cur.fetchall()]

    def recent_dialogue(self, limit: int = 10) -> list:
        cur = self.conn.execute(
            "SELECT role, content, created_at FROM conversations "
            "ORDER BY id DESC LIMIT ?", (limit,))
        return [{"role": r[0], "content": r[1], "created_at": r[2]}
                for r in cur.fetchall()]

    # ── 笔记 ────────────────────────────────────────────────
    def save_note(self, title: str, content: str, source_user_id: str = "user1") -> int:
        cur = self.conn.execute(
            "INSERT INTO notes (title, content, user_id) VALUES (?, ?, ?)",
            (title, content, source_user_id))
        self.conn.commit()
        note_id = cur.lastrowid
        # 向量化存储
        self._upsert_vector(
            doc_id=note_id,
            text=f"{title}\n{content}",
            payload={"type": "note", "title": title, "content": content,
                     "user_id": source_user_id}
        )
        return note_id

    def list_notes(self, limit: int = 10) -> list:
        """返回最近笔记列表，每项含 id, title, content。"""
        rows = self.conn.execute(
            "SELECT id, title, content FROM notes ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [{"id": r[0], "title": r[1], "content": r[2]} for r in rows]

    def delete_note(self, note_id: int) -> bool:
        """删除指定 ID 的笔记，返回是否成功。"""
        self.conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self.conn.commit()
        return self.conn.total_changes > 0

    def update_note(self, note_id: int, title: str, content: str) -> bool:
        """更新笔记标题和内容。"""
        self.conn.execute(
            "UPDATE notes SET title = ?, content = ?, updated_at = datetime('now') WHERE id = ?",
            (title, content, note_id))
        self.conn.commit()
        return self.conn.total_changes > 0

    def search_notes(self, keyword: str, limit: int = 5) -> list:
        cur = self.conn.execute(
            "SELECT title, content, created_at FROM notes "
            "WHERE content LIKE ? OR title LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit))
        return [{"title": r[0], "content": r[1], "created_at": r[2]}
                for r in cur.fetchall()]

    # ── 摘要 ────────────────────────────────────────────────
    def save_summary(self, segment_text: str, summary: str):
        self.conn.execute(
            "INSERT INTO summaries (segment_text, summary) VALUES (?, ?)",
            (segment_text, summary))
        self.conn.commit()

    def search_summaries(self, keyword: str, limit: int = 3) -> list:
        cur = self.conn.execute(
            "SELECT segment_text, summary, created_at FROM summaries "
            "WHERE segment_text LIKE ? OR summary LIKE ? "
            "ORDER BY id DESC LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit))
        return [{"segment_text": r[0], "summary": r[1], "created_at": r[2]}
                for r in cur.fetchall()]

    # ── 全文搜索（第二阶段：向量优先）──────────────────────
    def full_text_search(self, query: str, limit: int = 5) -> list:
        """向量检索优先，Qdrant 不可用时降级为关键词搜索。"""
        if self.qdrant is not None:
            results = self._vector_search(query, limit)
            if results:
                return results
        # 降级：关键词搜索
        return self.search_dialogue(query, limit) + self.search_notes(query, limit)

    def _vector_search(self, query: str, limit: int = 5) -> list:
        """Qdrant 向量检索。返回格式与关键词搜索一致。"""
        try:
            from src.memory.embedding import embed_query
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            vector = embed_query(query)
            if vector is None:
                return []
            search_result = self.qdrant.search(
                collection_name=self._qdrant_collection,
                query_vector=vector,
                limit=limit
            )
            results = []
            for hit in search_result:
                payload = hit.payload
                if payload.get("type") == "note":
                    results.append({
                        "title": payload.get("title", ""),
                        "content": payload.get("content", ""),
                        "created_at": "",
                        "score": hit.score
                    })
                else:
                    results.append({
                        "role": payload.get("role", ""),
                        "content": payload.get("content", ""),
                        "created_at": "",
                        "score": hit.score
                    })
            return results
        except Exception as e:
            warnings.warn(f"[warn] 向量检索失败（已降级）：{e}")
            return []

    # ── 清理 ────────────────────────────────────────────────
    def close(self):
        from src.memory.graph import close_driver
        close_driver()
        self.conn.close()
