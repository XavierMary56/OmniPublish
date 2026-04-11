#!/usr/bin/env python3
"""OmniPublish V2.0 — 后端集成测试

使用 FastAPI TestClient 测试全部 API 端点。
运行: cd backend && python -m pytest tests/ -v
"""

import json
import os
import sys
import pytest

# 确保 backend 在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from database import init_db

import asyncio


@pytest.fixture(scope="module", autouse=True)
def setup_db(tmp_path_factory):
    """测试前初始化临时数据库。"""
    tmp = tmp_path_factory.mktemp("data")
    db_path = str(tmp / "test.db")

    # 覆盖配置
    from config import settings
    settings.db_path = db_path

    # 覆盖 database 模块的 DB_PATH
    import database
    database.DB_PATH = db_path

    asyncio.run(init_db())


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client):
    """获取管理员 token。"""
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200
    data = res.json()
    assert data["code"] == 0
    return data["data"]["token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ════════════════════════════════════════
# 认证测试
# ════════════════════════════════════════

class TestAuth:
    def test_login_success(self, client):
        res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert res.status_code == 200
        data = res.json()
        assert data["code"] == 0
        assert "token" in data["data"]
        assert data["data"]["user"]["role"] == "admin"

    def test_login_wrong_password(self, client):
        res = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert res.status_code == 401

    def test_login_nonexistent_user(self, client):
        res = client.post("/api/auth/login", json={"username": "nobody", "password": "xxx"})
        assert res.status_code == 401

    def test_me_without_token(self, client):
        res = client.get("/api/auth/me")
        assert res.status_code == 401

    def test_me_with_token(self, client, admin_token):
        res = client.get("/api/auth/me", headers=auth_header(admin_token))
        assert res.status_code == 200
        assert res.json()["data"]["username"] == "admin"

    def test_create_user(self, client, admin_token):
        res = client.post("/api/auth/users", headers=auth_header(admin_token), json={
            "username": "editor1", "password": "pass1234",
            "display_name": "测试编辑", "dept": "1部4组", "role": "editor",
        })
        assert res.status_code == 200

    def test_create_duplicate_user(self, client, admin_token):
        res = client.post("/api/auth/users", headers=auth_header(admin_token), json={
            "username": "admin", "password": "pass1234",
            "display_name": "重复", "dept": "", "role": "editor",
        })
        assert res.status_code == 409

    def test_list_users(self, client, admin_token):
        res = client.get("/api/auth/users", headers=auth_header(admin_token))
        assert res.status_code == 200
        users = res.json()["data"]
        assert len(users) >= 2  # admin + editor1


# ════════════════════════════════════════
# 平台管理测试
# ════════════════════════════════════════

class TestPlatforms:
    def test_create_platform(self, client, admin_token):
        res = client.post("/api/platforms", headers=auth_header(admin_token), json={
            "name": "测试平台", "dept": "测试组",
            "categories": ["分类A", "分类B"],
            "img_wm_position": "bottom-right",
            "api_base_url": "https://test.example.com/api",
        })
        assert res.status_code == 200

    def test_list_platforms(self, client, admin_token):
        res = client.get("/api/platforms", headers=auth_header(admin_token))
        assert res.status_code == 200
        platforms = res.json()["data"]
        assert len(platforms) >= 1

    def test_update_platform(self, client, admin_token):
        # 先获取 ID
        res = client.get("/api/platforms", headers=auth_header(admin_token))
        pid = res.json()["data"][0]["id"]
        res = client.put(f"/api/platforms/{pid}", headers=auth_header(admin_token), json={
            "categories": ["新分类1", "新分类2", "新分类3"],
        })
        assert res.status_code == 200

    def test_filter_by_dept(self, client, admin_token):
        res = client.get("/api/platforms?dept=测试", headers=auth_header(admin_token))
        assert res.status_code == 200


# ════════════════════════════════════════
# 流水线测试
# ════════════════════════════════════════

class TestPipeline:
    def test_create_task_bad_folder(self, client, admin_token):
        res = client.post("/api/pipeline", headers=auth_header(admin_token), json={
            "folder_path": "/nonexistent/path", "target_platforms": [1],
        })
        assert res.status_code == 400

    def test_get_categories(self, client, admin_token):
        # 先创建平台确保有数据
        res = client.post("/api/platforms", headers=auth_header(admin_token), json={
            "name": "分类测试平台", "dept": "测试组", "categories": ["猫","狗"],
        })
        # 获取分类需要先有任务（需要 target_platforms），这里测试 404
        res = client.get("/api/pipeline/99999/step/2/categories", headers=auth_header(admin_token))
        assert res.status_code == 404

    def test_get_nonexistent_task(self, client, admin_token):
        res = client.get("/api/pipeline/99999", headers=auth_header(admin_token))
        assert res.status_code == 404


# ════════════════════════════════════════
# 任务看板测试
# ════════════════════════════════════════

class TestTasks:
    def test_list_tasks_empty(self, client, admin_token):
        res = client.get("/api/tasks", headers=auth_header(admin_token))
        assert res.status_code == 200
        data = res.json()["data"]
        assert "items" in data
        assert "total" in data

    def test_list_tasks_with_filter(self, client, admin_token):
        res = client.get("/api/tasks?status=running&search=test", headers=auth_header(admin_token))
        assert res.status_code == 200


# ════════════════════════════════════════
# 统计测试
# ════════════════════════════════════════

class TestStats:
    def test_overview(self, client, admin_token):
        res = client.get("/api/stats/overview?period=today", headers=auth_header(admin_token))
        assert res.status_code == 200
        data = res.json()["data"]
        assert "total" in data
        assert "success_rate" in data

    def test_platform_stats(self, client, admin_token):
        res = client.get("/api/stats/platforms?period=month", headers=auth_header(admin_token))
        assert res.status_code == 200

    def test_pipeline_timing(self, client, admin_token):
        res = client.get("/api/stats/pipeline-timing", headers=auth_header(admin_token))
        assert res.status_code == 200


# ════════════════════════════════════════
# 工具箱测试
# ════════════════════════════════════════

class TestTools:
    def test_copywrite_tool(self, client, admin_token):
        """文案生成工具（不实际调 API，测试端点可达）。"""
        res = client.post("/api/tools/copywrite", headers=auth_header(admin_token), json={
            "protagonist": "测试主角", "event": "测试事件",
        })
        # 如果没有配置 API Key，job 会快速失败，但端点应该返回 200
        assert res.status_code == 200
        assert "job_id" in res.json()["data"]

    def test_job_status_not_found(self, client, admin_token):
        res = client.get("/api/tools/nonexistent123/status", headers=auth_header(admin_token))
        assert res.status_code == 404


# ════════════════════════════════════════
# 权限测试
# ════════════════════════════════════════

class TestPermissions:
    def test_editor_cannot_create_platform(self, client, admin_token):
        """编辑不能管理业务线。"""
        # 先用 editor1 登录
        res = client.post("/api/auth/login", json={"username": "editor1", "password": "pass1234"})
        editor_token = res.json()["data"]["token"]

        res = client.post("/api/platforms", headers=auth_header(editor_token), json={
            "name": "非法平台", "dept": "xx",
        })
        assert res.status_code == 403

    def test_editor_cannot_create_user(self, client, admin_token):
        res = client.post("/api/auth/login", json={"username": "editor1", "password": "pass1234"})
        editor_token = res.json()["data"]["token"]

        res = client.post("/api/auth/users", headers=auth_header(editor_token), json={
            "username": "hack", "password": "1234567",
            "display_name": "非法", "role": "admin",
        })
        assert res.status_code == 403


# ════════════════════════════════════════
# 健康检查
# ════════════════════════════════════════

class TestHealth:
    def test_ping(self, client):
        res = client.get("/api/ping")
        assert res.status_code == 200
        assert res.json()["ok"] is True

    def test_info(self, client):
        res = client.get("/api/info")
        assert res.status_code == 200
        assert res.json()["version"] == "2.0.0"
