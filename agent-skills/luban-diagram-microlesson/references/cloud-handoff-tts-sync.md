# 云端 Claude Design 交接包 TTS 同步

适用范围：云端导出的自包含 DC 讲解/练习交接包。成品只落在
artifacts/luban_case_family_assets/diagram_microlesson/finished/<card-id>/；不改题目、判分、采分点或教学画面。

执行入口：python3 artifacts/luban_case_family_assets/diagram_microlesson/process_cloud_handoff_tts.py --job 'P40_A02=/absolute/path/A02.zip'

处理器按 cp437 -> gbk -> utf-8 解码 zip 文件名，识别上/中/下集和唯一练习页，生成老师 longanhuan_v3、学生 longlaotie_v3 的 per-beat 音频。问答幕按“学生问 + 0.4 秒静音 + 老师答”拼接；合成使用 CosyVoice cosyvoice-v3-flash、MP3、24 kHz、0.95 倍速、音量 65。

每个有文本的 beat 用 ffprobe 实测时长重排为“音频时长 + 0.5 秒缓冲”，同步更新 beats、DUR 和进度条 durSec。播放器同时注入音频启动/结束门控：画面时钟不得越过尚未播完的音频；没有旁白的纯画面 beat 保留原窗口。

已有同卡 audio/**/manifest.json 的 segment 文本逐字一致时复用原 mp3；其他文本才调用阿里云。每次实际合成前必须明确告知用户会使用 .env 的阿里云密钥并产生费用。

完成后至少验证：每页 tts-audit.json 的窗口余量非负、support.js 与音频可访问、讲解/练习互链目标存在、逐 beat CDP 截图无串台。真机/微信 WebView 从头听一遍仍是 autoplay 时序的最终验收。

