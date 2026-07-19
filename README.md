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

GitHub Issues 在线调用（像聊天机器人一样）：

1. fork 本项目到你的 GitHub 仓库（或者直接在当前仓库）。
2. 在你的仓库 `Settings -> Secrets and variables -> Actions` 中，点击 `New repository secret`，添加一个名为 `SILICONFLOW_API_KEY` 的 Secret，值为你的硅基流动 API Key。
3. 在你的仓库中，点击 `Issues` 标签页，创建一个 **New issue**。
4. 将你的抖音分享文本或链接写在 Issue 的标题或正文里，点击 `Submit new issue`。
5. 几秒钟后，GitHub Actions 机器人会自动执行提取，并将解析后的文案**以评论的形式**回复在这个 Issue 下！

TBD：长视频支持
- 智能落盘与切片 (Chunking)：检测文件体积，如果不超过 20MB 就继续用内存秒传；如果超过了，就下载到 GitHub Action 的临时硬盘里。然后利用 pydub 等音频处理库，将超长文件每隔 10 分钟切成一个小片段。
- 并发识别：将切出来的多个小片段并发或者排队发给硅基流动 API 进行识别。
- 取消硬编码超时：移除导致容易崩溃的 timeout=45 限制。