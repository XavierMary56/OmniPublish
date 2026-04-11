# OmniPublish V2.0 — API 接口文档

> 基础 URL: `http://localhost:9527`
> 交互式文档: `http://localhost:9527/docs` (Swagger UI)
> 认证方式: Bearer Token (JWT)

---

## 一、认证

### POST /api/auth/login

登录获取 JWT Token。

**请求体**:
```json
{"username": "admin", "password": "admin123"}
```

**响应**:
```json
{
  "code": 0,
  "data": {
    "token": "eyJhbGciOi...",
    "user": {"id": 1, "username": "admin", "display_name": "管理员", "dept": "系统", "role": "admin"}
  },
  "message": ""
}
```

**后续请求头**: `Authorization: Bearer <token>`

### GET /api/auth/me

获取当前用户信息。

### POST /api/auth/users (管理员)

创建新用户。

---

## 二、流水线（核心）

### POST /api/pipeline

创建发帖任务（Step 1 提交）。

**请求体**:
```json
{
  "folder_path": "/path/to/素材文件夹",
  "target_platforms": [1, 3, 5, 8, 12]
}
```

### GET /api/pipeline/{task_id}

获取任务完整详情（含 6 步状态 + 平台子任务）。

### GET /api/pipeline/{task_id}/step/2/categories

获取动态分类（根据已选平台取并集）。

**响应**:
```json
{
  "code": 0,
  "data": {
    "categories": ["今日吃瓜", "网红黑料", "热门大瓜", "学生校园"],
    "platforms_with_categories": 3,
    "total_platforms": 5
  }
}
```

### POST /api/pipeline/{task_id}/step/2/generate

触发 AI 文案生成（SSE 流式返回）。

### PUT /api/pipeline/{task_id}/step/2/confirm

确认文案，推进到 Step 3。

### PUT /api/pipeline/{task_id}/step/3/confirm

确认重命名，推进到 Step 4。

### PUT /api/pipeline/{task_id}/step/4/confirm

确认封面，推进到 Step 5。

### PUT /api/pipeline/{task_id}/step/5/confirm

确认水印方案，开始并行处理。

### POST /api/pipeline/{task_id}/step/6/publish

触发发布。

---

## 三、任务看板

### GET /api/tasks

任务列表（分页 + 筛选 + 搜索）。

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| status | string | 状态筛选: running/awaiting_confirm/done/failed |
| search | string | 搜索关键词（匹配 ID/标题） |
| page | int | 页码（默认 1） |
| limit | int | 每页条数（默认 20） |

### GET /api/tasks/{task_id}/logs

任务操作日志。

---

## 四、业务线管理

### GET /api/platforms

平台列表。参数 `?dept=1部` 按部组筛选。

### POST /api/platforms (管理员)

新增业务线。

### PUT /api/platforms/{id} (管理员)

编辑业务线。

### DELETE /api/platforms/{id} (管理员)

删除业务线（软删除）。

### POST /api/platforms/{id}/watermark/image (管理员)

上传图片水印文件（multipart/form-data）。

### POST /api/platforms/{id}/watermark/video (管理员)

上传视频水印文件。

### POST /api/platforms/{id}/categories/import (管理员)

批量导入分类库（上传 CSV/TXT 文件）。

---

## 五、WebSocket

### WS /ws/pipeline/{task_id}

流水线实时进度。

**推送事件**:
```json
{"type": "step_changed", "step": 1, "status": "done"}
{"type": "wm_progress", "platform_id": 3, "progress": 65.5}
{"type": "upload_progress", "platform_id": 3, "progress": 42.0}
{"type": "transcode_update", "platform_id": 3, "status": "done"}
{"type": "publish_result", "platform_id": 3, "status": "published"}
{"type": "task_completed", "task_id": 53}
```

### WS /ws/notifications

全局通知。

---

## 六、统一响应格式

```json
{
  "code": 0,        // 0=成功, 非0=错误
  "data": {},       // 响应数据
  "message": "ok"   // 提示信息
}
```

**错误码**:
| code | 含义 |
|------|------|
| 0 | 成功 |
| 400 | 参数错误 |
| 401 | 未认证 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 资源冲突（如重名） |
| 413 | 文件太大 |
| 500 | 服务端错误 |

---

## 七、默认账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 管理员 |
