#!/usr/bin/env python3
"""OmniPublish - AI 文案生成

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

import argparse, json, os, sys, urllib.request, urllib.error


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
        f"分类: {args.category}",
        "标题: <标题内容>",
        "关键词: <kw1,kw2,kw3,...>",
        "文案:",
        "<正文内容，段落间空一行>",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════
# API 调用
# ═══════════════════════════════════════════

def _is_anthropic(api_base, model):
    return "anthropic" in api_base.lower() or model.startswith("claude")


def call_api_openai(system_prompt, user_prompt, api_base, api_key, model):
    """调用 OpenAI 兼容 API（流式）。"""
    url = f"{api_base.rstrip('/')}/chat/completions"
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
        "User-Agent": "OmniPublish/1.0",
    })

    resp = urllib.request.urlopen(req, timeout=120)
    full_text = ""

    for raw_line in resp:
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
    """调用 Anthropic Messages API（流式）。"""
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
        "User-Agent": "OmniPublish/1.0",
    })

    resp = urllib.request.urlopen(req, timeout=120)
    full_text = ""

    for raw_line in resp:
        line = raw_line.decode().strip()
        if not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
            if chunk.get("type") == "content_block_delta":
                content = chunk.get("delta", {}).get("text", "")
                if content:
                    full_text += content
                    sys.stdout.write(content)
                    sys.stdout.flush()
        except (json.JSONDecodeError, KeyError, IndexError):
            continue

    return full_text


def call_api(system_prompt, user_prompt, api_base, api_key, model):
    """自动检测 API 类型并调用。"""
    if _is_anthropic(api_base, model):
        return call_api_anthropic(system_prompt, user_prompt, api_base, api_key, model)
    else:
        return call_api_openai(system_prompt, user_prompt, api_base, api_key, model)


# ═══════════════════════════════════════════
# 结果解析
# ═══════════════════════════════════════════

def parse_result(text, fallback_author, fallback_category):
    """从 AI 输出中解析结构化字段。"""
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

    for line in lines:
        s = line.strip()
        if not body_started:
            for prefix in ("作者:", "作者："):
                if s.startswith(prefix):
                    result["author"] = s[len(prefix):].strip()
                    break
            for prefix in ("分类:", "分类："):
                if s.startswith(prefix):
                    result["category"] = s[len(prefix):].strip()
                    break
            for prefix in ("标题:", "标题："):
                if s.startswith(prefix):
                    result["title"] = s[len(prefix):].strip()
                    break
            for prefix in ("关键词:", "关键词："):
                if s.startswith(prefix):
                    result["keywords"] = s[len(prefix):].strip()
                    break
            if s.startswith("文案:") or s.startswith("文案："):
                body_started = True
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
    ap.add_argument("--category", default="今日吃瓜")
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

    system_prompt = build_system_prompt(prompts_dir, args.style)
    user_prompt = build_user_prompt(args)

    if not api_key:
        # 无 API Key：输出组装好的 prompt 供用户手动复制
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
    print(f"[INFO] 正在调用 AI 生成文案...\n")

    # ── 调用 API ──
    try:
        full_text = call_api(system_prompt, user_prompt, api_base, api_key, model)
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else ""
        print(f"\n[ERROR] API 请求失败 (HTTP {e.code}): {body[:200]}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] API 调用失败: {e}")
        sys.exit(1)

    # ── 输出结构化结果（供前端 JS 解析）──
    result = parse_result(full_text, args.author, args.category)
    print(f"\n\n@@CW_RESULT@@{json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
