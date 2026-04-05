---
name: lightmerge
description: 管理 lightmerge 分支：从 zsw_main 重建 lightmerge 分支并合并指定分支。禁止直接修改 lightmerge 分支的代码。
---

# LightMerge 分支管理

用于管理 `lightmerge` 集成分支。该分支仅用于合并多个 fix/feature 分支后触发 CI 构建。

## 核心规则

**禁止直接在 lightmerge 分支上修改代码。** lightmerge 只做合并，不做代码变更。所有修改必须在各自的 fix/feature 分支或 zsw_main 上完成。

## 操作流程

当用户说 "lightmerge" 或要求合并分支到 lightmerge 时，按以下步骤执行：

### 1. 确认输入

获取用户要合并的分支列表。如果用户没有明确指定，则询问要合并哪些分支。

### 2. 切换到 zsw_main

```bash
git checkout zsw_main
```

### 3. 删除旧的 lightmerge 分支（本地+远端）

```bash
# 删除本地 lightmerge 分支
git branch -D lightmerge 2>/dev/null || true

# 删除远端 lightmerge 分支
git push myfork --delete lightmerge 2>/dev/null || true
```

### 4. 从 zsw_main 创建新的 lightmerge 分支

```bash
git checkout -b lightmerge
```

### 5. 依次合并指定分支

对每个要合并的分支：

```bash
git merge <branch-name> -m "Merge <branch-name> into lightmerge"
```

如果有冲突，报告给用户并暂停。

### 6. 更新合并记录

在 `lightmerge-merge-log.md` 文件中追加记录，格式：

```markdown
## lightmerge - YYYY-MM-DD HH:MM

### 合并分支
| 分支 | 最新提交 | 说明 |
|------|----------|------|
| zsw_main | abc1234 | 基础分支 |
| fix/xxx | def5678 | 修复描述 |
```

### 7. 推送到 myfork

```bash
git push myfork lightmerge
```

**注意：只推 myfork（zhushanwen321/Auto_Bangumi），不推 origin（EstrellaXD/Auto_Bangumi）。**

### 8. 切换回 zsw_main

```bash
git checkout zsw_main
```

## 注意事项

- lightmerge 分支名固定为 `lightmerge`，不再按日期命名
- 合并顺序：先 zsw_main（基础），再按用户指定的顺序合并其他分支
- 远端使用 `myfork`，不要推送到 `origin`
- 如果某个分支不存在，报告错误并跳过该分支继续合并其他分支
