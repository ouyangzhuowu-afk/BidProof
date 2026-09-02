# OCR Readiness

## 当前输入

- 扫描型招标 PDF：`work/uploads/8.20定稿-招标文件-塔里木河流域阿克苏河水利管理中心2027年信息化设计项目.pdf`
- 页数：78
- 本地文本抽取：0 字符
- 需要 OCR：78 页

## 运行状态

- OCR adapter：Qwen-VL-OCR，可替换
- 当前进程是否启用：是（通过 Windows 用户级 `QWEN_OCR_API_KEY` 临时注入，未写入项目）
- 最近一次运行：Qwen-VL-OCR 断点批处理已完成 78 页请求
- 结果：78 页 `EXTRACTED`，无失败页；第 52 页通过 `--retry-failed` 单页重试恢复。
- 第 52 页已渲染至 `work/previews/akss-page-52-52.png`，页面包含合同协议书正文；重试结果已保存为 `work/ocr/akss-water-it/page-0052.json`，可参与候选抽取，但仍需人工确认 quote 后才能作为正式 ground truth。

## 启用方式

运行方式（密钥只从环境变量读取，不写入项目）：

```powershell
$env:BID_OCR_PROVIDER = "qwen-vl-ocr"
$env:QWEN_OCR_API_KEY = "<从密钥管理器注入>"
uv run python -m work.ocr_batch "work/uploads/8.20定稿-招标文件-塔里木河流域阿克苏河水利管理中心2027年信息化设计项目.pdf" --output-dir work/ocr/akss-water-it --limit 3
```

本次 3 页 smoke run 成功；随后已执行完整 78 页断点批处理。第 52 页首次失败后使用 `--retry-failed` 恢复成功。任何后续 OCR 失败页仍必须保持 `FAILED/UNKNOWN`，不得进入 `PASS` 统计。
