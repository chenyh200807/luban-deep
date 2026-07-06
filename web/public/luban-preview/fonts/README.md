# 教学卡自托管字体子集

微信 web-view 加载 fonts.googleapis.com 外链静默失败（无报错、直接回落系统字体），
所以发布管线（`scripts/publish_luban_preview_cards.py`）把卡里的 Google Fonts 外链
替换为本目录的自托管子集。

- `NotoSansSC-luban-subset.woff2` — Noto Sans SC 可变字体（wght 100-900 轴保留）
- `LongCang-luban-subset.woff2` — Long Cang（海报书法字）

子集字符集 = `artifacts/luban_case_family_assets/diagram_microlesson/finished/` 全部
`*.dc.html`（含 JS 内旁白/QA 文案）出现过的字符 ∪ ASCII 可打印 ∪ 常用中文标点符号。
新卡若引入子集外的生僻字，需重新生成（否则该字回落系统字体，不会消失）。

重新生成（源字体来自 google/fonts 仓库 OFL 目录）：

```bash
pip install fonttools brotli
curl -sL -o NotoSansSC.ttf "https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf"
curl -sL -o LongCang.ttf  "https://github.com/google/fonts/raw/main/ofl/longcang/LongCang-Regular.ttf"
# subset.txt = 按上述规则收集的字符集合（一行全量字符）
pyftsubset NotoSansSC.ttf --text-file=subset.txt --flavor=woff2 --output-file=NotoSansSC-luban-subset.woff2
pyftsubset LongCang.ttf  --text-file=subset.txt --flavor=woff2 --output-file=LongCang-luban-subset.woff2
```

许可：两款字体均为 SIL Open Font License 1.1，允许子集化与自托管分发。
