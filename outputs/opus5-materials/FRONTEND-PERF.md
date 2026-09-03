# 前端性能实测（试点）

日期：2026-09-04  
URL：https://bidproof.marketcase.net/app  
方法：浏览器 CDP `performance` + 本机构建产物 gzip + HTTP 头

## Web Vitals / Navigation

| 指标 | 值 |
|---|---|
| FCP | 1344 ms |
| DOMContentLoaded | 1339 ms |
| Load Event | 1339 ms |
| responseStart（文档） | 945 ms |
| `/app` 请求耗时（脚本侧） | ~526 ms |

## 静态资源体积

| 文件 | Raw | Gzip（本地 Optimal） | 网络 transferSize |
|---|---|---|---|
| `static/app.js` | 80,519 B | 19,923 B（19.5 KB） | ~20.9 KB |
| `static/style.css` | 56,491 B | — | ~12.9 KB |
| `lucide.min.js` | — | — | encoded ~88 KB（本次 transferSize=0，可能磁盘缓存） |

构建：`frontend/` Vite `minify: esbuild`，`minifyIdentifiers: false`（保留 UI 契约函数名）。

## Cache-Control

```
GET /static/app.js?v=20260904-1
Cache-Control: max-age=14400
cf-cache-status: HIT
ETag: W/"…"
```

HTML `/app` 未设置长期 Cache-Control（动态认证页）。静态资源依赖 query string 版本戳（`?v=20260904-1`）。

## 安全响应头（同源页面）

试点已返回：`Content-Security-Policy`、`X-Content-Type-Options=nosniff`、`X-Frame-Options=DENY`、`Referrer-Policy`、`Permissions-Policy`。

## Lighthouse

本次未生成完整 Lighthouse JSON。可复现：

```bash
npx lighthouse https://bidproof.marketcase.net/app --only-categories=performance --output=json --output-path=./lighthouse.json
```
