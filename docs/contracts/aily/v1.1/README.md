# Aily / 豆包工作伙伴 v1.1 contracts

Inbound conversation connector. 豆包 understands natural language and must
call this system's kernel for engineering numbers.

**Live outbound Feishu session:** `AILY_OUTBOUND_LIVE_SESSION=NO`

## Artifacts

| File | Purpose |
| --- | --- |
| `aily-to-system-zone-plan.openapi.yaml` | Custom connector OpenAPI for `POST /api/v1/aily/v1/zone-plan` |
| `doubao-skill.v1.md` | Paste-ready 豆包工作伙伴 skill (Chinese conversation policy) |
| `doubao-skill.v1.json` | Structured companion for tests and tooling |

## 豆包 skill notes

- 吨 = 每天。用户说「多少吨的加工厂」只是口语例子；豆包负责听懂，本系统不解析聊天。
- 五个参数：每天进货公斤、成品天数、冻果天数、主包材天数、辅包材天数。
- 调用前把吨/天换成 `daily_inbound_mass_kg`（kg/day；1 吨/天 = 1000 kg/day）。
- 缺哪个就问哪个。不要自己编面积。
- 调用本接口后，把 `markdown_table` 原样发给用户。
- 标明这是概念设计，需要复核。
