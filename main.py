import io
import os
import sys
import re
import requests

# ==================== 配置区域 ====================
# 1. douyin.wtf 混合解析接口
DOUYIN_ONLINE_API = "https://douyin.wtf/api/hybrid/video_data"

# 2. 硅基流动的 API Key 和请求地址
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_ASR_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
SILICONFLOW_LLM_URL = "https://api.siliconflow.cn/v1/chat/completions"

# 3. 选择语音识别模型 (推荐阿里 SenseVoiceSmall，速度快且自带标点)
ASR_MODEL = "FunAudioLLM/SenseVoiceSmall"

# 4. 选择文案润色 LLM (Qwen/Qwen3-8B 为硅基流动永久免费、中文能力强)
LLM_MODEL = "Qwen/Qwen3-8B"
# ==================================================

# 文案润色的系统 Prompt
LLM_SYSTEM_PROMPT = """你是一名专业的短视频文案编辑。
你的任务是将用户提供的语音识别原文（通常无标点、含大量口语废话）润色成一份干净、易读的书面文案。

处理规则：
1. 去除口语废话词：「呃」「啊」「那个」「然后」「就是说」「嗯」「对吧」「你知道吧」等。
2. 补全标点符号（逗号、句号、问号、感叹号等），让句子结构清晰。
3. 按照语义逻辑合理分段，每段约 2~4 句话，不要整段塞在一起。
4. 保留原文的核心信息和表达风格，不要过度增加、删减或改写语义。
5. 仅输出润色后的正文，不要附加任何说明、前言或后记。"""


def get_douyin_media_url(share_text_or_url: str) -> tuple[str, str]:
    """第一步：调用 /api/hybrid/video_data，提取优先音频或无水印视频地址

    返回: (media_url, media_type) -> ("https://...", "mp3"|"mp4")
    """
    print("1. 正在调用 douyin.wtf 混合解析接口...")

    # 从分享文本中提取真正的 URL，防止多余的字符导致 API 400 错误
    url_match = re.search(r'(https?://[-A-Za-z0-9+&@#/%?=~_|!:,.;]+[-A-Za-z0-9+&@#/%=~_|])', share_text_or_url)
    clean_url = url_match.group(1) if url_match else share_text_or_url

    # 设置请求参数
    params = {
        "url": clean_url,
        "minimal": "true",  # 开启精简模式，加快接口返回速度
    }

    try:
        response = requests.get(DOUYIN_ONLINE_API, params=params, timeout=15)
        response.raise_for_status()
        res_json = response.json()

        # 检查接口 HTTP 状态码与业务 code
        if res_json.get("code") != 200:
            raise RuntimeError(f"API 解析返回异常: {res_json}")

        data = res_json.get("data", {})
        if not data:
            raise ValueError("解析成功，但未能获取到有效的数据结构(data为空)。")

        # --- 策略：优先拿纯音频(省带宽极速识别)，拿不到再拿无水印视频 ---
        # 1. 尝试获取独立背景音乐/音频
        music_url_list = (
            data.get("music", {}).get("play_url", {}).get("url_list", [])
        )
        if music_url_list and music_url_list[0]:
            print(" -> 成功获取纯音频流地址！(耗时更短、带宽更省)")
            return music_url_list[0], "mp3"

        # 2. 尝试获取无水印视频流
        video_url_list = (
            data.get("video", {}).get("play_addr", {}).get("url_list", [])
        )
        if video_url_list and video_url_list[0]:
            print(" -> 成功获取无水印视频流地址！")
            return video_url_list[0], "mp4"

        raise ValueError("无法从接口返回的数据中提取到有效的音频或视频下载链接。")

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"网络请求失败，无法连接到 douyin.wtf API: {e}")


def transcribe_via_siliconflow(media_url: str, media_type: str) -> str:
    """第二与第三步：在内存中拉取流媒体，并直接发给硅基流动进行 ASR 识别"""
    print("2. 正在拉取音视频流数据（纯内存操作，不写入硬盘）...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    media_response = requests.get(
        media_url, headers=headers, stream=True, timeout=20
    )
    media_response.raise_for_status()

    # 将拉取到的二进制数据压入内存流
    media_buffer = io.BytesIO(media_response.content)
    # 根据类型动态赋予后缀名，让 API 能够正确识别编码格式
    media_buffer.name = f"audio.{media_type}"

    print(f"3. 正在将数据发送至硅基流动 ({ASR_MODEL}) 进行识别...")
    auth_headers = {"Authorization": f"Bearer {SILICONFLOW_API_KEY}"}
    files = {
        "file": (
            media_buffer.name,
            media_buffer,
            f"audio/{media_type}"
            if media_type == "mp3"
            else f"video/{media_type}",
        )
    }
    payload = {
        "model": ASR_MODEL,
        "response_format": "json",  # 支持 "json", "text", "srt" 等
    }

    res = requests.post(
        SILICONFLOW_ASR_URL,
        headers=auth_headers,
        files=files,
        data=payload,
        timeout=45,
    )

    if res.status_code == 200:
        return res.json().get("text", "")
    else:
        raise RuntimeError(
            f"硅基流动语音识别失败 [{res.status_code}]: {res.text}"
        )



def polish_transcript_via_llm(raw_text: str) -> str:
    """第四步：调用硅基流动 LLM 将 ASR 原文润色为分段、有标点的书面文案

    参数:
        raw_text: 语音识别输出的原始文本（通常无标点、含口语废话）

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
    }

    res = requests.post(
        SILICONFLOW_LLM_URL,
        headers=headers,
        json=payload,
        timeout=60,
    )

    if res.status_code == 200:
        return res.json()["choices"][0]["message"]["content"].strip()
    else:
        raise RuntimeError(
            f"硅基流动 LLM 润色失败 [{res.status_code}]: {res.text}"
        )


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

        # 3. LLM 润色
        polished = polish_transcript_via_llm(transcript)

        print(
            "\n================ 润色后文案 ================"
        )
        print(polished)
        print(
            "============================================\n"
        )

        # 将 ASR 原始口播文案写入文件
        with open("transcript.txt", "w", encoding="utf-8") as f:
            f.write(transcript)

        # 将润色后的书面文案写入文件，方便外部流程（如 GitHub Action）直接读取
        with open("polished.txt", "w", encoding="utf-8") as f:
            f.write(polished)

    except Exception as err:
        print(f"\n❌ 运行出错: {err}")