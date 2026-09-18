import io
import json
import os
import sys
import re
import time
import requests

# ==================== 配置区域 ====================
# 1. 解析接口：默认指向 douyin.wtf，可通过环境变量 DOUYIN_API_BASE 覆盖（如自建 Docker 实例）
_api_base = os.environ.get("DOUYIN_API_BASE", "https://douyin.wtf").rstrip("/")
DOUYIN_ONLINE_API = _api_base + "/api/hybrid/video_data"

# 2. 硅基流动的 API Key、请求地址与超时设置
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_ASR_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
SILICONFLOW_LLM_URL = "https://api.siliconflow.cn/v1/chat/completions"
# 读取超时时间（秒），应对长音视频和跨国网络延迟，默认 180 秒
SILICONFLOW_TIMEOUT = int(os.environ.get("SILICONFLOW_TIMEOUT", "180"))

# 3. 选择语音识别模型 (推荐阿里 SenseVoiceSmall，速度快且自带标点)
ASR_MODEL = "FunAudioLLM/SenseVoiceSmall"

# 4. 选择文案润色 LLM (Qwen/Qwen3-8B 为硅基流动永久免费、中文能力强)
LLM_MODEL = "Qwen/Qwen3-8B"
# ==================================================

# 文案润色的系统 Prompt
LLM_SYSTEM_PROMPT = """你是一名专业的语音文稿校对员。
你的唯一任务是对语音识别原文做**最小干预的格式清洗**，绝对不允许删减、合并、总结或改写任何实质性内容。

## 允许做的事（仅限以下操作）
1. **去除口语填充词**：仅删除无实际含义的口语废词，如「呃」「啊」「那个」「嗯」「就是说」「对吧」「你知道吧」「当然了」（独立成分时）等，但如果这些词承载了情绪或转折含义则保留。
2. **补全标点**：添加逗号、句号、问号、感叹号、引号、书名号等，使句子结构清晰。
3. **合理分段**：在明显的话题转折、逻辑切换或语义边界处，插入空行（即连续两个换行符 \n\n）将全文分为若干自然段，每段 3～8 句为宜。不改变任何内容，不合并句子。

## 严格禁止的事
- 禁止删除任何一句话、任何一个论点、任何一个举例，哪怕你觉得它"重复"或"不重要"。
- 禁止将多句话合并成一句总结性表达。
- 禁止改写、替换、重新组织句子的顺序或结构。

## 输出格式要求
- 段落之间必须有空行（\n\n）
- 禁止将全文输出为无换行的连续长段
- 禁止在正文之外添加任何前言、后记、标题或说明。

## 目标
输出的文本应与原文**信息量完全一致**，只是更干净、更易读、分段清晰。
原文有多少信息，输出就有多少信息，一句都不能少。"""


def get_douyin_media_url(share_text_or_url: str) -> tuple[str, str]:
    """第一步：调用 /api/hybrid/video_data，提取优先音频或无水印视频地址

    返回: (media_url, media_type) -> ("https://...", "mp3"|"mp4")
    """
    if "douyin.wtf" in DOUYIN_ONLINE_API:
        print("1. 正在调用 douyin.wtf 混合解析接口...")
    else:
        print(f"1. 正在调用自定义/本地解析接口 ({_api_base})...")

    # 从分享文本中提取真正的 URL，防止多余的字符导致 API 400 错误
    url_match = re.search(r'(https?://[-A-Za-z0-9+&@#/%?=~_|!:,.;]+[-A-Za-z0-9+&@#/%=~_|])', share_text_or_url)
    clean_url = url_match.group(1) if url_match else share_text_or_url

    # 设置请求参数
    params = {
        "url": clean_url,
        "minimal": "true",  # 开启精简模式，加快接口返回速度
    }

    try:
        response = requests.get(DOUYIN_ONLINE_API, params=params, timeout=60)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        if "douyin.wtf" not in DOUYIN_ONLINE_API:
            print(f" -> [Warn] 本地/自定义接口请求失败 ({e})，正在自动切换至 douyin.wtf 官方接口重试...")
            try:
                response = requests.get("https://douyin.wtf/api/hybrid/video_data", params=params, timeout=60)
                response.raise_for_status()
            except requests.exceptions.RequestException as e2:
                raise RuntimeError(f"网络请求失败，本地和官方 API 均无法连接: {e2}")
        else:
            raise RuntimeError(f"网络请求失败，无法连接到 douyin.wtf API: {e}")

    try:
        res_json = response.json()

        # 检查接口 HTTP 状态码与业务 code
        if res_json.get("code") != 200:
            raise RuntimeError(f"API 解析返回异常: {res_json}")

        data = res_json.get("data", {})
        if not data:
            raise ValueError("解析成功，但未能获取到有效的数据结构(data为空)。")

        # --- 策略：优先拿无水印视频流（保证包含口播人声+伴奏完整音轨），拿不到再降级尝试独立音频 ---
        # 1. 优先尝试获取无水印视频流（包含完整口播录音）
        video_url_list = (
            data.get("video", {}).get("play_addr", {}).get("url_list", [])
        )
        if video_url_list and video_url_list[0]:
            print(" -> 成功获取无水印视频流地址！(包含完整口播与原声)")
            return video_url_list[0], "mp4"

        # 2. 尝试获取无水印视频流 (新版 video_data 结构)
        nwm_video_url = data.get("video_data", {}).get("nwm_video_url")
        if nwm_video_url:
            print(" -> 成功获取无水印视频流地址(新版结构)！(包含完整口播与原声)")
            return nwm_video_url, "mp4"

        # 3. 降级备用：尝试获取独立背景音乐/音频（仅适用于纯音频条目或未提取到视频的作品）
        music_url_list = (
            data.get("music", {}).get("play_url", {}).get("url_list", [])
        )
        if music_url_list and music_url_list[0]:
            print(" -> [降级备用] 未获取到视频流，正在使用独立音频流...")
            return music_url_list[0], "mp3"

        print(" -> [Debug] 无法提取有效链接，API 原始返回数据如下：")
        print(json.dumps(res_json, ensure_ascii=False, indent=2))
        raise ValueError("无法从接口返回的数据中提取到有效的音频或视频下载链接。")

    except ValueError as e:
        raise e


def transcribe_via_siliconflow(media_url: str, media_type: str, max_retries: int = 3) -> str:
    """第二与第三步：在内存中拉取流媒体，并直接发给硅基流动进行 ASR 识别（带自动重试与超时保护）"""
    print("2. 正在拉取音视频流数据（纯内存操作，不写入硬盘）...")

    cookie = os.environ.get("DOUYIN_COOKIE", "")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
    }
    if cookie:
        headers["Cookie"] = cookie

    media_response = requests.get(
        media_url, headers=headers, stream=True, timeout=(10, 60)
    )
    media_response.raise_for_status()

    # 将拉取到的二进制数据压入内存流
    raw_content = media_response.content
    media_buffer = io.BytesIO(raw_content)
    media_buffer.name = f"audio.{media_type}"
    media_size_mb = len(raw_content) / (1024 * 1024)

    print(
        f"3. 正在将数据发送至硅基流动 ({ASR_MODEL}) 进行识别 "
        f"(大小: {media_size_mb:.2f}MB, 单次读取超时: {SILICONFLOW_TIMEOUT}s)..."
    )
    auth_headers = {"Authorization": f"Bearer {SILICONFLOW_API_KEY}"}
    payload = {
        "model": ASR_MODEL,
        "response_format": "json",  # 支持 "json", "text", "srt" 等
    }

    last_err = None
    for attempt in range(1, max_retries + 1):
        # 每次重试前必须重置内存文件指针，否则后续重试发送的数据为空
        media_buffer.seek(0)
        files = {
            "file": (
                media_buffer.name,
                media_buffer,
                f"audio/{media_type}"
                if media_type == "mp3"
                else f"video/{media_type}",
            )
        }

        try:
            if attempt > 1:
                print(f" -> [ASR 重试] 正在进行第 {attempt}/{max_retries} 次转录请求...")

            res = requests.post(
                SILICONFLOW_ASR_URL,
                headers=auth_headers,
                files=files,
                data=payload,
                timeout=(15, SILICONFLOW_TIMEOUT),
            )

            if res.status_code == 200:
                return res.json().get("text", "")

            # 针对服务端偶发 502/503/504 错误进行退避重试
            if res.status_code in (502, 503, 504) and attempt < max_retries:
                wait_seconds = attempt * 3
                print(f" -> [Warn] 硅基流动服务端偶发繁忙 [{res.status_code}]，等待 {wait_seconds}s 后重试...")
                time.sleep(wait_seconds)
                continue

            raise RuntimeError(
                f"硅基流动语音识别失败 [{res.status_code}]: {res.text}"
            )

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_err = e
            if attempt < max_retries:
                wait_seconds = attempt * 3
                print(f" -> [Warn] ASR 请求超时或连接异常 ({e})，等待 {wait_seconds}s 后重试 ({attempt}/{max_retries})...")
                time.sleep(wait_seconds)
            else:
                raise RuntimeError(
                    f"硅基流动语音识别超时或网络异常（已重试 {max_retries} 次，当前单次读取超时限制为 {SILICONFLOW_TIMEOUT}s）: {e}\n"
                    f"💡 提示：对于长音频或海外网络环境，可设置环境变量 SILICONFLOW_TIMEOUT 进一步调大超时时间（例如 300）"
                ) from e
        except Exception as e:
            raise e

    if last_err:
        raise last_err



def polish_transcript_via_llm(raw_text: str, max_retries: int = 3) -> str:
    """第四步：调用硅基流动 LLM 将 ASR 原文润色为分段、有标点的书面文案（带自动重试）

    参数:
        raw_text: 语音识别输出的原始文本（通常无标点、含口语废话）
        max_retries: 最大重试次数，默认 3 次

    返回:
        polished_text: 润色后的书面文案字符串
    """
    print(f"4. 正在调用 {LLM_MODEL} 进行文案润色...")

    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        # 关闭思维链，直接输出结果（Qwen3 特有参数）
        "extra_body": {"enable_thinking": False},
        "temperature": 0.3,   # 低温度保证结果稳定、不过度发散
        "max_tokens": 4096,
        "stream": True,       # 开启流式输出，边生成边打印，避免长文本超时
    }

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                print(f" -> [LLM 重试] 正在进行第 {attempt}/{max_retries} 次润色请求...")

            # timeout=(连接超时, 读取超时)：连接 15s，单次读取 120s
            res = requests.post(
                SILICONFLOW_LLM_URL,
                headers=headers,
                json=payload,
                timeout=(15, 120),
                stream=True,
            )

            if res.status_code != 200:
                if res.status_code in (502, 503, 504) and attempt < max_retries:
                    wait_seconds = attempt * 3
                    print(f" -> [Warn] 硅基流动 LLM 服务端临时繁忙 [{res.status_code}]，等待 {wait_seconds}s 后重试...")
                    time.sleep(wait_seconds)
                    continue
                raise RuntimeError(
                    f"硅基流动 LLM 润色失败 [{res.status_code}]: {res.text}"
                )

            # 逐行解析 SSE 数据流，实时打印并拼接完整文本
            print("\n================ 润色后文案 ================")
            full_content = []
            has_started_printing = False
            for line in res.iter_lines():
                if not line:
                    continue
                # SSE 格式：每行以 "data: " 开头
                text = line.decode("utf-8") if isinstance(line, bytes) else line
                if not text.startswith("data:"):
                    continue
                data_str = text[len("data:"):].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    if not has_started_printing:
                        token = token.lstrip()
                        if not token:
                            continue
                        has_started_printing = True
                    print(token, end="", flush=True)
                    full_content.append(token)

            print("\n============================================\n")
            return "".join(full_content).strip()

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_err = e
            if attempt < max_retries:
                wait_seconds = attempt * 3
                print(f" -> [Warn] LLM 请求超时或连接异常 ({e})，等待 {wait_seconds}s 后重试 ({attempt}/{max_retries})...")
                time.sleep(wait_seconds)
            else:
                raise RuntimeError(
                    f"硅基流动 LLM 润色超时或网络异常（已重试 {max_retries} 次）: {e}"
                ) from e
        except Exception as e:
            raise e

    if last_err:
        raise last_err


# ==================== 实际运行测试 ====================
if __name__ == "__main__":
    # 优先使用命令行传入的分享文本或链接
    if len(sys.argv) > 1:
        share_text_or_url = " ".join(sys.argv[1:])
    else:
        # 默认测试链接
        share_text_or_url = "https://v.douyin.com/jWOixl-zwTI/"

    try:
        # 1. 拿取媒体播放地址，以及对应是 mp3 还是 mp4
        real_media_url, m_type = get_douyin_media_url(share_text_or_url)

        # 2. 语音转文字
        transcript = transcribe_via_siliconflow(real_media_url, m_type)

        print(
            "\n================ ASR 原始文案 ================"
        )
        print(transcript)
        print(
            "=============================================\n"
        )

        # 校验 ASR 识别结果是否包含有效口播文本
        # 过滤掉纯标点、空白字符、无声占位符（如 '..', '...', '<|nospeech|>' 等）
        valid_chars = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]', transcript)
        if not valid_chars:
            raise ValueError(
                "未从该作品音视频中检测到有效口播语音（该作品可能是图文笔记、纯背景音乐/无解说视频，或录音声音过小）。"
            )

        # 3. LLM 润色（函数内部已实时打印流式输出，无需在此重复打印）
        polished = polish_transcript_via_llm(transcript)

        # 将 ASR 原始口播文案写入文件
        with open("transcript.txt", "w", encoding="utf-8") as f:
            f.write(transcript)

        # 将润色后的书面文案写入文件，方便外部流程（如 GitHub Action）直接读取
        with open("polished.txt", "w", encoding="utf-8") as f:
            f.write(polished)

    except Exception as err:
        print(f"\n❌ 运行出错: {err}")
        sys.exit(1)