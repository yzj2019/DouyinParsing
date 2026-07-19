[![Powered by Douyin_TikTok_Download_API](https://img.shields.io/badge/Powered%20by-Douyin__TikTok__Download__API-000000?style=for-the-badge&logo=tiktok&logoColor=white)](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)

极简实现，用 Douyin_TikTok_Download_API 提供的在线 API 获取无水印视频，用硅基流动的 FunAudioLLM/SenseVoiceSmall 模型做语音转文字 ASR

本地调用：

```powershell
# 将硅基流动的 API Key 配置进环境变量 SILICONFLOW_API_KEY
$env:SILICONFLOW_API_KEY="你的API Key"

# 运行默认测试链接
python .\main.py

# 附加抖音分享文本或链接
python .\main.py "你的分享文本或链接"
```
