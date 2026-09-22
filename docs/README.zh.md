# AIMarket Playground

[English](../README.md) · [Русский](README.ru.md) · [Español](README.es.md) · [Français](README.fr.md) · **中文** · [术语表](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)

无需配置即可运行真实路径：**调用 GAIA → Metis 验证 → 已签名的 Hub 收据**。

## 用途

Playground 只执行 allowlist 中的一项 workflow，不会运行浏览器提交的任意代码。代码面板解释
真实 HTTP 路径，服务器执行有边界的请求，浏览器不会获得基础设施密钥。

```text
浏览器 → AIMarket Playground → Hub → GAIA → Metis → 已验证收据 → Alien Monitor
```

GAIA 返回 LIVE 读数。系统使用来源 Hub 的公钥验证 Ed25519 收据；仅存在 `signature` 字段不算
完成验证。读数和已验证的收据会先显示；Metis 随后在后台异步验证并显示计时状态。Metis
不可用时，结果会如实显示 `PARTIAL`，绝不会伪装成 `VERIFIED`。Playground 的外部等待时限为
620 秒。默认情况下，Playground 通过 `fast` 路径向 Metis 发送明确的内部一致性检查任务；
`/v1/verify` 仍会运行真实验证方，因此普通读数不会启动完整 Council/MoA。缺少
`verify_performed: true` 的响应会显示为**未检查**，不会伪装成真实的零分裁决；旧版或错误配置
的部署会按 fail-closed 处理。Metis 服务端时限为 600 秒，Playground 总任务预算为 640 秒。
Metis 返回的 `verified` flag 表示其自身评估通过了验证方检查，并不表示 GAIA 读数自动通过合理性
检查。只有当评估包含结构化 `VERDICT: plausible` 且 Hub 收据已验证时，Playground 才显示
`VERIFIED`；不合理或非结构化的评估保持为 `PARTIAL`。
对于需要认证的 production Metis，请仅在服务器端设置 `PLAYGROUND_METIS_KEY`；浏览器永远不会获得该密钥。
各种结束状态会分别显示。

## 本地运行

```bash
uv sync --extra dev
uv run pytest
uv run uvicorn playground.app:app --host 127.0.0.1 --port 8075
```

打开 <http://127.0.0.1:8075/?lang=zh>。

## Docker

```bash
docker compose up --build
```

Compose 仅在 `127.0.0.1` 发布端口，使用只读 filesystem，移除 Linux capabilities，限制进程数，
添加 health check，并启用 `no-new-privileges`。公共部署必须在前方配置 HTTPS reverse proxy 和外部 rate limit。

## 配置与安全

从 `.env.example` 开始。Hub、GAIA 和 Metis URL 默认必须使用 HTTPS。配置
`PLAYGROUND_EVENT_URL` 时必须同时提供 `PLAYGROUND_EVENT_TOKEN`。`PLAYGROUND_MAX_*` 限制使用量、
并发数、upstream 响应大小和运行历史。限制同时绑定匿名访客和网络来源；轮换 browser visitor ID
不能绕过预算保护。通过密码学验证的收据还必须匹配请求的 `product_id`、`capability_id` 和成功调用。

## 产品边界

Use Cases Portal 展示机会和生态地图；Playground 通过一次真实调用启用开发者；
`create-aimarket-agent` 创建由开发者掌控的代码仓库。三者是连续阶段，不是重复门户。

`读数`、`收据`、`验证`和`轨道`遵循规范术语表。品牌、代码、标识符、CLI 命令、env vars、URL、
`LIVE` 和 `SIM` 保持不变。

## 许可证

MIT — 参见 [LICENSE](../LICENSE)。
