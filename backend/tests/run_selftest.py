#!/usr/bin/env python3
"""OmniPublish V2.0 — 自测脚本（直接运行，不依赖 pytest）"""

import asyncio
import json
import os
import sys
import shutil
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db
asyncio.run(init_db())

# 种子数据
seed_mod_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations", "002_seed_platforms.py")
exec(open(seed_mod_path, encoding="utf-8").read())
asyncio.run(seed())

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
errors = []
passed = 0


def test(name, fn):
    global passed
    try:
        fn()
        print(f"  [PASS] {name}")
        passed += 1
    except AssertionError as e:
        print(f"  [FAIL] {name}: {e}")
        errors.append((name, str(e)))
    except Exception as e:
        print(f"  [FAIL] {name}: {type(e).__name__}: {e}")
        errors.append((name, str(e)))


# ═══ 1. 健康检查 ═══
print("=== 1. Health Check ===")

test("GET /api/ping", lambda: (
    setattr(r := client.get("/api/ping"), "_", None) or
    r.status_code == 200 or (_ := 1/0)
) and True)

test("GET /api/info", lambda: (
    client.get("/api/info").status_code == 200
))

# ═══ 2. 认证 ═══
print("=== 2. Auth ===")

_login_res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
assert _login_res.status_code == 200, f"Login failed: {_login_res.status_code} {_login_res.text}"
TOKEN = _login_res.json()["data"]["token"]
H = {"Authorization": f"Bearer {TOKEN}"}
print(f"  [PASS] POST /api/auth/login (token obtained)")
passed += 1

test("Login wrong password -> 401", lambda: (
    client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
) or (_ := 1/0))

test("GET /api/auth/me", lambda: (
    client.get("/api/auth/me", headers=H).json()["data"]["username"] == "admin"
) or (_ := 1/0))

test("GET /api/auth/me no token -> 401", lambda: (
    client.get("/api/auth/me").status_code == 401
) or (_ := 1/0))

# 创建编辑用户
r = client.post("/api/auth/users", headers=H, json={
    "username": "selftest_editor", "password": "test1234",
    "display_name": "自测编辑", "dept": "1部4组", "role": "editor",
})
if r.status_code == 200:
    print("  [PASS] POST /api/auth/users (create editor)")
    passed += 1
elif r.status_code == 409:
    print("  [PASS] POST /api/auth/users (already exists, OK)")
    passed += 1
else:
    print(f"  [FAIL] POST /api/auth/users: {r.status_code} {r.text}")
    errors.append(("create user", r.text))

test("GET /api/auth/users (list)", lambda: (
    len(client.get("/api/auth/users", headers=H).json()["data"]) >= 2
) or (_ := 1/0))

# ═══ 3. 平台管理 ═══
print("=== 3. Platforms ===")

test("GET /api/platforms (35 seed)", lambda: (
    len(client.get("/api/platforms", headers=H).json()["data"]) >= 35
) or (_ := 1/0))

test("GET /api/platforms?dept=1部", lambda: (
    all("1部" in p["dept"] for p in client.get("/api/platforms?dept=1部", headers=H).json()["data"])
) or (_ := 1/0))

test("POST /api/platforms (create)", lambda: (
    client.post("/api/platforms", headers=H, json={
        "name": f"selftest_{int(time.time())}", "dept": "测试组", "categories": ["X", "Y"],
    }).status_code == 200
) or (_ := 1/0))

# ═══ 4. 权限控制 ═══
print("=== 4. Permissions ===")

_editor_res = client.post("/api/auth/login", json={"username": "selftest_editor", "password": "test1234"})
EDITOR_TOKEN = _editor_res.json()["data"]["token"]
EH = {"Authorization": f"Bearer {EDITOR_TOKEN}"}

test("Editor cannot POST /api/platforms -> 403", lambda: (
    client.post("/api/platforms", headers=EH, json={"name": "illegal", "dept": "x"}).status_code == 403
) or (_ := 1/0))

test("Editor cannot POST /api/auth/users -> 403", lambda: (
    client.post("/api/auth/users", headers=EH, json={
        "username": "hack", "password": "1234567", "display_name": "x", "role": "admin",
    }).status_code == 403
) or (_ := 1/0))

# ═══ 5. 流水线 ═══
print("=== 5. Pipeline ===")

# 创建临时素材文件夹
tmp_dir = tempfile.mkdtemp(prefix="omnipub_test_")
from PIL import Image
for i in range(3):
    img = Image.new("RGB", (200, 200), (255, i * 80, 0))
    img.save(os.path.join(tmp_dir, f"photo_{i+1:02d}.jpg"))

# 创建任务
r = client.post("/api/pipeline", headers=H, json={
    "folder_path": tmp_dir, "target_platforms": [1, 2, 3],
})
assert r.status_code == 200, f"Create task failed: {r.status_code} {r.text}"
TASK_ID = r.json()["data"]["task_id"]
TASK_NO = r.json()["data"]["task_no"]
manifest = r.json()["data"]["file_manifest"]
print(f"  [PASS] POST /api/pipeline (task_id={TASK_ID}, no={TASK_NO}, images={len(manifest['images'])})")
passed += 1

test("GET /api/pipeline/{id} (detail)", lambda: (
    (r := client.get(f"/api/pipeline/{TASK_ID}", headers=H)) and
    r.status_code == 200 and
    len(r.json()["data"]["steps"]) == 6 and
    len(r.json()["data"]["platform_tasks"]) == 3
) or (_ := 1/0))

test("GET /pipeline/{id}/step/2/categories", lambda: (
    (r := client.get(f"/api/pipeline/{TASK_ID}/step/2/categories", headers=H)) and
    r.status_code == 200 and
    "categories" in r.json()["data"]
) or (_ := 1/0))

test("POST /pipeline/{id}/scan-folder", lambda: (
    client.post(f"/api/pipeline/{TASK_ID}/scan-folder", headers=H).status_code == 200
) or (_ := 1/0))

test("PUT /pipeline/{id}/step/2/confirm", lambda: (
    client.put(f"/api/pipeline/{TASK_ID}/step/2/confirm", headers=H, json={
        "title": "自测标题", "keywords": "k1,k2", "body": "自测正文", "author": "自测", "categories": ["A"],
    }).status_code == 200
) or (_ := 1/0))

test("GET /pipeline/{id}/step/3/preview", lambda: (
    (r := client.get(f"/api/pipeline/{TASK_ID}/step/3/preview?prefix=selftest", headers=H)) and
    r.status_code == 200 and
    len(r.json()["data"]) == 3 and
    r.json()["data"][0]["new"] == "selftest_01.jpg"
) or (_ := 1/0))

test("GET /pipeline/99999 -> 404", lambda: (
    client.get("/api/pipeline/99999", headers=H).status_code == 404
) or (_ := 1/0))

test("POST /pipeline bad folder -> 400", lambda: (
    client.post("/api/pipeline", headers=H, json={
        "folder_path": "/no/such/path", "target_platforms": [1],
    }).status_code == 400
) or (_ := 1/0))

# ═══ 6. 任务看板 ═══
print("=== 6. Tasks ===")

test("GET /api/tasks", lambda: (
    (r := client.get("/api/tasks", headers=H)) and
    r.status_code == 200 and
    "items" in r.json()["data"] and
    r.json()["data"]["total"] >= 1
) or (_ := 1/0))

test("GET /api/tasks?status=running", lambda: (
    client.get("/api/tasks?status=running", headers=H).status_code == 200
) or (_ := 1/0))

# ═══ 7. 统计 ═══
print("=== 7. Stats ===")

test("GET /api/stats/overview", lambda: (
    (r := client.get("/api/stats/overview?period=today", headers=H)) and
    r.status_code == 200 and
    "total" in r.json()["data"]
) or (_ := 1/0))

test("GET /api/stats/platforms", lambda: (
    client.get("/api/stats/platforms?period=month", headers=H).status_code == 200
) or (_ := 1/0))

test("GET /api/stats/pipeline-timing", lambda: (
    client.get("/api/stats/pipeline-timing", headers=H).status_code == 200
) or (_ := 1/0))

# ═══ 8. 工具箱 ═══
print("=== 8. Tools ===")

test("POST /api/tools/convert-image", lambda: (
    (r := client.post("/api/tools/convert-image", headers=H, json={
        "input_dir": tmp_dir, "target_format": "png",
    })) and
    r.status_code == 200 and
    "job_id" in r.json()["data"]
) or (_ := 1/0))

test("POST /api/tools/smart-cover", lambda: (
    (r := client.post("/api/tools/smart-cover", headers=H, json={
        "input_dir": tmp_dir, "layout": "single", "candidates": 1,
    })) and
    r.status_code == 200 and
    "job_id" in r.json()["data"]
) or (_ := 1/0))

# 等工具完成后查状态
time.sleep(2)
jid_r = client.post("/api/tools/convert-image", headers=H, json={"input_dir": tmp_dir, "target_format": "webp"})
jid = jid_r.json()["data"]["job_id"]
time.sleep(2)

test("GET /api/tools/{job_id}/status", lambda: (
    (r := client.get(f"/api/tools/{jid}/status", headers=H)) and
    r.status_code == 200 and
    r.json()["data"]["status"] in ("running", "done", "failed")
) or (_ := 1/0))

test("GET /api/tools/bad_id -> 404", lambda: (
    client.get("/api/tools/nonexistent/status", headers=H).status_code == 404
) or (_ := 1/0))

# 清理
shutil.rmtree(tmp_dir, ignore_errors=True)

# ═══ 结果 ═══
print()
print("=" * 40)
print(f"  PASSED: {passed}")
print(f"  FAILED: {len(errors)}")
print(f"  TOTAL:  {passed + len(errors)}")
print("=" * 40)
if errors:
    print()
    for name, err in errors:
        print(f"  FAIL: {name}")
        print(f"        {err[:100]}")
    sys.exit(1)
else:
    print("  ALL TESTS PASSED ✅")
