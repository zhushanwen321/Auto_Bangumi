# 代码修复计划

## 概述
- 批次：batch-20260407-ai-dandanplay-integration
- 生成时间：2026-04-07
- 一般问题数：12
- 轻微问题数：8

## 优先修复（7分）

| 优先级 | 问题描述 | 文件 | 修复建议 |
|--------|----------|------|----------|
| P0 | AIMatcher 不支持 Azure OpenAI | ai_matcher.py | 参考 OpenAIParser（parser/analyser/openai.py:64-72），当 api_type=="azure" 时使用 AzureOpenAI 客户端并传入 deployment_id 和 api_version |

## 计划修复（5-6分）

| 优先级 | 问题描述 | 文件 | 修复建议 |
|--------|----------|------|----------|
| P1 | Mikan parser 异常处理不完整 | analyser.py | 将 `except AttributeError` 改为 `except (AttributeError, TypeError)`，或在调用 mikan_parser 前检查 torrent.homepage 非 None |
| P1 | tmdb_matched 语义不准确 | analyser.py | 重命名为 `title_enhanced`，Mikan 成功时验证返回值非空后再设为 True |
| P1 | _lookup_offsets 死代码 | renamer.py | 标记为 deprecated 或清理（需同步清理 test/test_renamer.py 中的约 10 处引用） |
| P1 | config.py fire-and-forget | config.py | 保存 task 引用到 Program 实例，或在 stop 时 await |
| P2 | analyser.py 竞态条件 | analyser.py | 将 ORM 对象转为 dict 后再传入 asyncio.create_task，与 config.py 的处理方式一致 |
| P2 | json.loads 缺少异常处理 | ai_matcher.py | 在 _call_llm 中 try-except json.JSONDecodeError，记录明确错误日志 |
| P2 | resp.json() 缺少异常处理 | dandanplay.py | 在 search() 中 try-except httpx.JSONDecodeError，不消耗重试次数 |

## 可选优化（3-5分）

| 问题描述 | 文件 | 优化建议 |
|----------|------|----------|
| dandanplay/advance gen_path 分支重复 | renamer.py | dandanplay 分支直接复用 advance 的返回值 |
| season_offset 参数未使用 | renamer.py | 清理整条传递链路中的 season_offset 参数 |
| fetch_dandanplay_title 死代码 | dandanplay.py | 删除该函数及其测试文件 |
| _batch_lookup_offsets 异常过宽 | renamer.py | 区分 DatabaseError（回退到 0）和其他 Exception（记录 warning） |
| DandanplayThread 无条件启动 | sub_thread.py | 考虑在 start() 中添加条件检查（与 RSS/Rename 一致） |

## 执行建议

1. **P0（Azure 支持）** 影响面最大但只影响 Azure 用户，可根据用户反馈决定是否在本迭代修复
2. **P1 中 Mikan 异常处理和 tmdb_matched 语义** 是最值得修复的，改动小、收益明确
3. **P1 中 _lookup_offsets 和 P2 中的代码质量问题** 可在后续重构中处理
4. 可选优化均为代码卫生/风格改进，不影响功能正确性
