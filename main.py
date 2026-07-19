import io
import os
import requests

# ==================== 配置区域 ====================
# 1. douyin.wtf 混合解析接口
DOUYIN_ONLINE_API = "https://douyin.wtf/api/hybrid/video_data"

# 2. 硅基流动的 API Key 和请求地址
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_ASR_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"

# 3. 选择语音识别模型 (推荐阿里 SenseVoiceSmall，速度快且自带标点)
ASR_MODEL = "FunAudioLLM/SenseVoiceSmall"
# ==================================================


def get_douyin_media_url(share_text_or_url: str) -> tuple[str, str]:
    """第一步：调用 /api/hybrid/video_data，提取优先音频或无水印视频地址

    返回: (media_url, media_type) -> ("https://...", "mp3"|"mp4")
    """
    print("1. 正在调用 douyin.wtf 混合解析接口...")

    # 根据文档截图，设置请求参数
    params = {
        "url": share_text_or_url,
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


# ==================== 实际运行测试 ====================
if __name__ == "__main__":
    # 截图文档提示 url 支持“分享文本、短链或长链”
    # 你可以直接把抖音里点击“复制链接”的那一整串文字贴进来，比如：
    # "7.23 03/24 复制打开抖音，看看【xxxx的作品】... https://v.douyin.com/iLxxxxx/"
    test_share_url = "https://v.douyin.com/jBMTBIxMpEU/"

    try:
        # 1. 拿取媒体播放地址，以及对应是 mp3 还是 mp4
        real_media_url, m_type = get_douyin_media_url(test_share_url)

        # 2. 语音转文字
        transcript = transcribe_via_siliconflow(real_media_url, m_type)

        print(
            "\n================ 解析成功！文案内容如下 ================"
        )
        print(transcript)
        print(
            "========================================================\n"
        )
    except Exception as err:
        print(f"\n❌ 运行出错: {err}")