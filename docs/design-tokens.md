# BidProof 设计 Token 映射

可执行定义：`frontend/src/styles/tokens.css`。界面继续使用现有原生 ES 模块、Vite 与语义 CSS，不引入组件框架或远程字体。旧变量通过别名对接新变量，避免旧页和新工作台出现两套颜色。

| 语义 | CSS Variables | 浅色主题值 |
| --- | --- | --- |
| 画布 / 卡片 / 次级表面 | `--canvas` / `--paper` / `--paper-sunken` | `#F4F5F7` / `#FFFFFF` / `#FAFAFA` |
| 正文 / 次要正文 / 元数据 | `--ink` / `--ink-soft` / `--ink-muted` | `#243237` / `#526168` / `#68757B` |
| 默认 / 强边界 | `--rule` / `--rule-strong` | `#E5E7EB` / `#D1D5DB` |
| 主动作 / 悬停 / 选中底色 | `--brand` / `--brand-hover` / `--brand-wash` | `#0F766E` / `#115E59` / `#EDF6F4` |
| 致命 / 不满足 | `--verdict-fail` / `--verdict-fail-wash` / `--verdict-fail-line` | `#B42332` / `#FEF2F2` / `#F2CCD0` |
| 待人工复核 | `--verdict-review` / `--verdict-review-wash` / `--verdict-review-line` | `#996014` / `#FFFBEB` / `#EEDDB6` |
| 核销通过 | `--verdict-pass` / `--verdict-pass-wash` / `--verdict-pass-line` | `#087F5B` / `#ECFDF5` / `#BFE5D5` |
| 引文高亮 | `--quote-highlight` | `#F3E8B7` |
| 导航底色 / 当前页 | `--nav-bg` / `--nav-active` | `#FAFAFA` / `#EDF6F4` |
| 页面标题与关键计数 | `--text-2xl`、兼容 `--text-3xl` | 20px |
| 区块标题 | `--text-lg`、兼容 `--text-xl` | 16px |
| 正文与主要操作 | `--text-md` / `--text-sm` | 14px |
| 辅助信息 | `--text-xs` / `--text-2xs` | 12px |
| 行高 | `--leading-tight` / `--leading-body` / `--leading-cite` | 1.5 / 1.6 / 1.6 |
| 间距 | `--space-1` 至 `--space-16` | 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64px |
| 控件 / 卡片 / 浮窗圆角 | `--radius-control` / `--radius-card` / `--radius-overlay` | 6 / 12 / 14px |
| 卡片阴影 | `--shadow-card` | `0 1px 3px rgb(0 0 0 / 5%), 0 10px 15px -5px rgb(0 0 0 / 2%)` |
| 导航宽度 | `--sidebar-w` | 208px |
| 状态过渡 | `--dur-fast` / `--dur-slow` | 160 / 240ms；减少动效时归零 |

字体使用系统无衬线栈，中文优先苹方、微软雅黑。关键计数不另开超大字号，通过位置、字重、分隔与留白建立焦点。颜色必须与中文状态同时出现，不能仅靠红绿传递结论。

现有别名：`--primary → --brand`、`--surface → --paper`、`--muted → --ink-muted`、`--line → --rule`、`--sidebar-width → --sidebar-w`、`--pass/fail/review → 对应 verdict 色`。兼容既有管理和决策页，深色模式继续沿用现有主题机制。

`UNKNOWN` 仍为“未找到证据”，`NEEDS_REVIEW` 为“待人工确认”；FATAL 是条款类别，PASS/FAIL 是判定状态，二者不可作为互斥状态混用。
