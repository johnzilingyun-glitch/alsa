"""
Prompt模板版本控制：管理Prompt版本，支持A/B测试
"""
import sqlite3
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime


class PromptVersionManager:
    """Prompt模板版本管理器"""
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # 默认路径
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            db_path = os.path.join(root_dir, "data", "prompt_versions.db")
        
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self._init_table()
    
    def _init_table(self):
        """初始化数据库表"""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                template TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metrics JSON,
                active BOOLEAN DEFAULT 0,
                UNIQUE(name, version)
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS ab_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version_a TEXT NOT NULL,
                version_b TEXT NOT NULL,
                split_ratio REAL DEFAULT 0.5,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                metrics_a JSON,
                metrics_b JSON,
                status TEXT DEFAULT 'active'
            )
        """)
        self.db.commit()
    
    def create_version(
        self, 
        name: str, 
        version: str, 
        template: str, 
        description: str = "",
        activate: bool = False
    ) -> int:
        """
        创建新的prompt版本
        
        Args:
            name: prompt名称（如 'technical_analyst'）
            version: 版本号（如 'v1', 'v2'）
            template: 模板内容
            description: 版本描述
            activate: 是否立即激活
            
        Returns:
            版本ID
        """
        cursor = self.db.execute(
            "INSERT INTO prompt_versions (name, version, template, description, active) VALUES (?, ?, ?, ?, ?)",
            (name, version, template, description, 1 if activate else 0)
        )
        
        if activate:
            # 停用其他版本
            self.db.execute(
                "UPDATE prompt_versions SET active = 0 WHERE name = ? AND version != ?",
                (name, version)
            )
        
        self.db.commit()
        return cursor.lastrowid
    
    def get_active_prompt(self, name: str) -> Optional[Dict[str, Any]]:
        """获取当前激活的prompt版本"""
        row = self.db.execute(
            "SELECT id, version, template, description, created_at FROM prompt_versions WHERE name = ? AND active = 1",
            (name,)
        ).fetchone()
        
        if row:
            return {
                "id": row[0],
                "version": row[1],
                "template": row[2],
                "description": row[3],
                "created_at": row[4]
            }
        return None
    
    def get_version(self, name: str, version: str) -> Optional[Dict[str, Any]]:
        """获取指定版本的prompt"""
        row = self.db.execute(
            "SELECT id, template, description, created_at, active FROM prompt_versions WHERE name = ? AND version = ?",
            (name, version)
        ).fetchone()
        
        if row:
            return {
                "id": row[0],
                "template": row[1],
                "description": row[2],
                "created_at": row[3],
                "active": bool(row[4])
            }
        return None
    
    def list_versions(self, name: str) -> List[Dict[str, Any]]:
        """列出所有版本"""
        rows = self.db.execute(
            "SELECT id, version, description, created_at, active FROM prompt_versions WHERE name = ? ORDER BY created_at DESC",
            (name,)
        ).fetchall()
        
        return [
            {
                "id": r[0],
                "version": r[1],
                "description": r[2],
                "created_at": r[3],
                "active": bool(r[4])
            }
            for r in rows
        ]
    
    def activate_version(self, name: str, version: str) -> bool:
        """激活指定版本"""
        # 检查版本存在
        if not self.get_version(name, version):
            return False
        
        # 停用所有版本
        self.db.execute("UPDATE prompt_versions SET active = 0 WHERE name = ?", (name,))
        
        # 激活指定版本
        self.db.execute(
            "UPDATE prompt_versions SET active = 1 WHERE name = ? AND version = ?",
            (name, version)
        )
        
        self.db.commit()
        return True
    
    def delete_version(self, name: str, version: str) -> bool:
        """删除指定版本（不能删除激活版本）"""
        # 检查是否为激活版本
        active = self.get_active_prompt(name)
        if active and active["version"] == version:
            return False
        
        self.db.execute(
            "DELETE FROM prompt_versions WHERE name = ? AND version = ?",
            (name, version)
        )
        self.db.commit()
        return True
    
    def update_metrics(self, name: str, version: str, metrics: Dict[str, Any]):
        """更新版本性能指标"""
        self.db.execute(
            "UPDATE prompt_versions SET metrics = ? WHERE name = ? AND version = ?",
            (json.dumps(metrics), name, version)
        )
        self.db.commit()
    
    def start_ab_test(
        self, 
        name: str, 
        version_a: str, 
        version_b: str, 
        split_ratio: float = 0.5
    ) -> int:
        """启动A/B测试"""
        cursor = self.db.execute(
            "INSERT INTO ab_tests (name, version_a, version_b, split_ratio, start_time, status) VALUES (?, ?, ?, ?, ?, 'active')",
            (name, version_a, version_b, split_ratio, datetime.now().isoformat())
        )
        self.db.commit()
        return cursor.lastrowid
    
    def get_ab_test_variant(self, test_id: int, user_id: str) -> str:
        """根据用户ID确定A/B测试变体（确保一致性）"""
        import hash
        
        test = self.db.execute(
            "SELECT split_ratio FROM ab_tests WHERE id = ? AND status = 'active'",
            (test_id,)
        ).fetchone()
        
        if not test:
            return "a"  # 默认返回A
        
        # 使用用户ID哈希确保同一用户总是看到同一变体
        hash_value = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        return "a" if (hash_value % 100) < (test[0] * 100) else "b"
    
    def stop_ab_test(self, test_id: int, metrics_a: Dict, metrics_b: Dict):
        """停止A/B测试并记录结果"""
        self.db.execute(
            "UPDATE ab_tests SET end_time = ?, metrics_a = ?, metrics_b = ?, status = 'completed' WHERE id = ?",
            (datetime.now().isoformat(), json.dumps(metrics_a), json.dumps(metrics_b), test_id)
        )
        self.db.commit()
    
    def get_ab_test_results(self, test_id: int) -> Optional[Dict[str, Any]]:
        """获取A/B测试结果"""
        row = self.db.execute(
            "SELECT * FROM ab_tests WHERE id = ?",
            (test_id,)
        ).fetchone()
        
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "version_a": row[2],
                "version_b": row[3],
                "split_ratio": row[4],
                "start_time": row[5],
                "end_time": row[6],
                "metrics_a": json.loads(row[7]) if row[7] else None,
                "metrics_b": json.loads(row[8]) if row[8] else None,
                "status": row[9]
            }
        return None


# 单例
prompt_version_manager = PromptVersionManager()
