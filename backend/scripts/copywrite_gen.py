#!/usr/bin/env python3
"""OmniPublish - AI 文案生成

改进点:
- API 调用失败 3 次指数退避重试
- --category 支持逗号分隔多分类
- Anthropic SSE 处理 error/message_stop 事件
- 流式读取增加 socket 超时保护
- 输出改为 JSON Lines 格式

用法:
    python3 copywrite_gen.py --protagonist "张三" --event "被拍到深夜约会" \
        --photos "3张自拍、海边写真" --video-desc "餐厅亲密画面" \
        --style "反转打脸风" --body-len 300 --paragraphs 3

配置:
    API 设置从 ../config.json 读取，也可通过环境变量覆盖:
    - OPENAI_API_BASE  (默认 https://api.openai.com/v1)
    - OPENAI_API_KEY
    - CW_MODEL         (默认 gpt-4o)

Prompt 模板:
    scripts/cw_prompts/ 目录下的纯文本文件:
    - base_instruction.txt     底色指令
    - article_structure.txt    文章结构
    - style_XXX.txt            各文风模板
"""

import argparse, json, os, re, sys, time, urllib.request, urllib.error


# ═══════════════════════════════════════════
# Style parameter validation
# ═══════════════════════════════════════════

def _validate_style(style: str) -> str:
    """Sanitize style parameter: only allow alphanumeric, Chinese characters, hyphens, underscores."""
    if not re.match(r'^[\w\u4e00-\u9fff-]+$', style):
        print(f"[ERROR] Invalid style parameter: {style}", file=sys.stderr)
        print("[ERROR] Style must only contain letters, digits, Chinese characters, hyphens, underscores.", file=sys.stderr)
        sys.exit(1)
    return style


# ═══════════════════════════════════════════
# Prompt 加载与组装
# ═══════════════════════════════════════════

def read_txt(path):
    """读取文本文件，不存在则返回空字符串。"""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def build_system_prompt(prompts_dir, style_name):
    """组装 system prompt = 底色指令 + 文章结构 + 文风模板"""
    parts = []

    base = read_txt(os.path.join(prompts_dir, "base_instruction.txt"))
    if base:
        parts.append(base)

    structure = read_txt(os.path.join(prompts_dir, "article_structure.txt"))
    if structure:
        parts.append(structure)

    style = read_txt(os.path.join(prompts_dir, f"style_{style_name}.txt"))
    if style:
        parts.append(f"【本次文风：{style_name}】\n{style}")

    if not parts:
        print("[WARN] cw_prompts/ 目录下没有找到任何 prompt 文件")

    return "\n\n".join(parts)


def build_user_prompt(args):
    """组装 user prompt = 素材 + 要求 + 输出格式"""
    # 分类字段处理：支持逗号分隔多分类
    category_str = args.category
    if isinstance(category_str, list):
        category_str = ",".join(category_str)

    lines = [
        "请根据以下素材生成文案：",
        "",
        f"【主角】{args.protagonist}",
        f"【事件】{args.event}",
    ]
    if args.photos:
        lines.append(f"【生活照】{args.photos}")
    if args.video_desc:
        lines.append(f"【视频内容】{args.video_desc}")

    lines += [
        "",
        "【输出要求】",
        f"标题：{args.title_min}~{args.title_max}字，吸引点击",
        f"关键词：{args.kw_count}个，英文逗号分隔",
        f"正文：约{args.body_len}字，分{args.paragraphs}段",
        "",
        "【输出格式】严格按以下格式输出，不要添加多余标记：",
        f"作者: {args.author}",
        f"分类: {category_str}",
        "标题: <标题内容>",
        "关键词: <kw1,kw2,kw3,...>",
        "文案:",
        "<正文内容，段落间空一行>",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════
# API 调用（带重试）
# ═══════════════════════════════════════════

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # 秒


def _is_anthropic(api_base, model):
    """判断是否使用 Anthropic 原生 API（非 OpenAI 兼容中转）。"""
    base_lower = api_base.lower()
    # 只有直连 Anthropic 官方 API 时才走 Anthropic 协议
    # 第三方中转站（即使模型名包含 claude）统一走 OpenAI 兼容协议
    return "anthropic.com" in base_lower or "api.anthropic" in base_lower


def _read_stream_with_timeout(resp, timeout_per_line=60):
    """带单行超时的流式读取。"""
    try:
        import socket
        if hasattr(resp, 'fp') and hasattr(resp.fp, '_sock'):
            resp.fp._sock.settimeout(timeout_per_line)
        elif hasattr(resp, 'fp') and hasattr(resp.fp, 'raw') and hasattr(resp.fp.raw, '_sock'):
            resp.fp.raw._sock.settimeout(timeout_per_line)
    except (AttributeError, OSError):
        pass  # 在线程池中可能无法设置 socket timeout，忽略
    for raw_line in resp:
        yield raw_line


def call_api_openai(system_prompt, user_prompt, api_base, api_key, model):
    """调用 OpenAI 兼容 API（流式）。"""
    base = api_base.rstrip('/')
    # 自动补 /v1 前缀（如果用户没写）
    if not base.endswith('/v1'):
        base += '/v1'
    url = f"{base}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "temperature": 0.8,
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "OmniPublish/2.0",
    })

    resp = urllib.request.urlopen(req, timeout=120)
    full_text = ""

    for raw_line in _read_stream_with_timeout(resp):
        line = raw_line.decode().strip()
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
            content = chunk["choices"][0].get("delta", {}).get("content", "")
            if content:
                full_text += content
                sys.stdout.write(content)
                sys.stdout.flush()
        except (json.JSONDecodeError, KeyError, IndexError):
            continue

    return full_text


def call_api_anthropic(system_prompt, user_prompt, api_base, api_key, model):
    """调用 Anthropic Messages API（流式），处理完整事件类型。"""
    base = api_base.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    url = f"{base}/messages"
    payload = json.dumps({
        "model": model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "temperature": 0.8,
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "User-Agent": "OmniPublish/2.0",
    })

    resp = urllib.request.urlopen(req, timeout=120)
    full_text = ""

    for raw_line in _read_stream_with_timeout(resp):
        line = raw_line.decode().strip()
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
            event_type = chunk.get("type", "")

            if event_type == "content_block_delta":
                content = chunk.get("delta", {}).get("text", "")
                if content:
                    full_text += content
                    sys.stdout.write(content)
                    sys.stdout.flush()
            elif event_type == "error":
                error_msg = chunk.get("error", {}).get("message", "Unknown error")
                raise RuntimeError(f"Anthropic API error: {error_msg}")
            elif event_type == "message_stop":
                break

        except json.JSONDecodeError:
            continue

    return full_text


def call_api(system_prompt, user_prompt, api_base, api_key, model):
    """自动检测 API 类型并调用，失败时指数退避重试。"""
    fn = call_api_anthropic if _is_anthropic(api_base, model) else call_api_openai
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(system_prompt, user_prompt, api_base, api_key, model)
        except urllib.error.HTTPError as e:
            body = e.read().decode() if hasattr(e, "read") else ""
            last_error = f"HTTP {e.code}: {body[:200]}"
            # 4xx 客户端错误不重试（除 429）
            if 400 <= e.code < 500 and e.code != 429:
                print(f"\n[ERROR] API 请求失败 (不可重试): {last_error}")
                raise RuntimeError(f"API 请求失败: {last_error}")
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES:
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            print(f"\n[WARN]  第 {attempt} 次调用失败: {last_error}")
            print(f"[WARN]  {delay} 秒后重试 ({attempt}/{MAX_RETRIES})...")
            time.sleep(delay)

    print(f"\n[ERROR] API 调用失败，已重试 {MAX_RETRIES} 次: {last_error}")
    raise RuntimeError(f"API 调用失败 (重试 {MAX_RETRIES} 次): {last_error}")


# ═══════════════════════════════════════════
# 结果解析（增强健壮性）
# ═══════════════════════════════════════════

def parse_result(text, fallback_author, fallback_category):
    """从 AI 输出中解析结构化字段。支持全角/半角冒号、前后空格容错。"""
    result = {
        "author": fallback_author,
        "category": fallback_category,
        "title": "",
        "keywords": "",
        "body": "",
    }

    lines = text.strip().split("\n")
    body_started = False
    body_lines = []

    # 冒号匹配模式：支持全角、半角、前后有空格
    colon_pattern = r'\s*[:：]\s*'

    for line in lines:
        s = line.strip()
        if not body_started:
            m = re.match(r'^作者' + colon_pattern + r'(.+)$', s)
            if m:
                result["author"] = m.group(1).strip()
                continue
            m = re.match(r'^分类' + colon_pattern + r'(.+)$', s)
            if m:
                result["category"] = m.group(1).strip()
                continue
            m = re.match(r'^标题' + colon_pattern + r'(.+)$', s)
            if m:
                result["title"] = m.group(1).strip()
                continue
            m = re.match(r'^关键词' + colon_pattern + r'(.+)$', s)
            if m:
                result["keywords"] = m.group(1).strip()
                continue
            if re.match(r'^文案' + colon_pattern + r'$', s) or s in ("文案:", "文案："):
                body_started = True
                continue
        else:
            body_lines.append(line)

    result["body"] = "\n".join(body_lines).strip()
    return result


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="OmniPublish AI Copywriter")
    ap.add_argument("--protagonist", required=True, help="主角")
    ap.add_argument("--event", required=True, help="事件")
    ap.add_argument("--photos", default="", help="生活照描述")
    ap.add_argument("--video-desc", default="", help="视频内容描述")
    ap.add_argument("--style", default="反转打脸风", help="文风")
    ap.add_argument("--title-min", type=int, default=20)
    ap.add_argument("--title-max", type=int, default=30)
    ap.add_argument("--kw-count", type=int, default=5)
    ap.add_argument("--body-len", type=int, default=300)
    ap.add_argument("--paragraphs", type=int, default=3)
    ap.add_argument("--author", default="编辑")
    # 分类支持逗号分隔多值
    ap.add_argument("--category", default="今日吃瓜",
                    help="分类，支持逗号分隔多值如 '今日吃瓜,网红黑料'")
    ap.add_argument("--api-base", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    # ── 路径 ──
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompts_dir = os.path.join(script_dir, "cw_prompts")
    config_file = os.path.join(script_dir, "..", "config.json")

    # ── 配置 ──
    config = {}
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

    api_base = args.api_base or os.environ.get("ANTHROPIC_BASE_URL") or os.environ.get("OPENAI_API_BASE") or config.get("api_base", "")
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY") or config.get("api_key", "")
    model = args.model or os.environ.get("ANTHROPIC_MODEL") or os.environ.get("CW_MODEL") or config.get("cw_model", "")

    # ── 加载 prompt 模板 ──
    if not os.path.isdir(prompts_dir):
        print(f"[ERROR] 找不到 prompt 模板目录: {prompts_dir}")
        sys.exit(1)

    system_prompt = build_system_prompt(prompts_dir, _validate_style(args.style))
    user_prompt = build_user_prompt(args)

    if not api_key:
        print("[INFO] 未配置 API Key，输出完整 prompt 供手动使用")
        print("[INFO] 如需自动生成，请在 config.json 填入 api_key\n")
        print("=" * 50)
        print("【System Prompt】")
        print("=" * 50)
        print(system_prompt)
        print("\n" + "=" * 50)
        print("【User Prompt】")
        print("=" * 50)
        print(user_prompt)
        sys.exit(0)

    print(f"[INFO] 文风: {args.style} | 模型: {model}")
    print(f"[INFO] 正在调用 AI 生成文案（最多重试 {MAX_RETRIES} 次）...\n")

    # ── 调用 API（带重试）──
    full_text = call_api(system_prompt, user_prompt, api_base, api_key, model)

    # ── 输出结构化结果（JSON Lines 格式）──
    result = parse_result(full_text, args.author, args.category)
    print(f"\n\n@@CW_RESULT@@{json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
