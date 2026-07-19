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

GitHub Actions 在线调用：

1. fork 本项目到你的 GitHub 仓库（或者直接在当前仓库）。
2. 在你的仓库 `Settings -> Secrets and variables -> Actions` 中，点击 `New repository secret`，添加一个名为 `SILICONFLOW_API_KEY` 的 Secret，值为你的硅基流动 API Key。
3. 在你的仓库 `Actions` 页面中，选择左侧的 `抖音文案解析 (Douyin Parsing)` 工作流。
4. 点击 `Run workflow`，在弹出的输入框中填入抖音分享文本或链接，点击执行。
5. 等待执行完成后，点击进入该次执行记录的 `Run parser` 步骤，即可看到解析并转换后的文案内容。
