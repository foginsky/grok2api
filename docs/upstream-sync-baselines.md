# Upstream Sync Baselines

用于记录本仓库每次同步上游时所依据的基线提交，方便下次只检查这些基线之后的新变化，减少重复比对工作量。

## Current recorded baseline

记录时间：2026-03-24

### Local fork landing point (before current image/config selective sync commits)

- Repository: `git@github-account-b:foginsky/grok2api.git`
- Branch: `main`
- Synced local commit: `3e40ce3a166dad341520ab2ec1027185db4462e5`
- Commit summary: `2026-03-19 docs: update upstream sync review baselines`

### Upstream: XianYuDaXian/grok2api

- Remote name: `upstream_xianyu`
- Repository: `https://github.com/XianYuDaXian/grok2api`
- Synced reference branch: `upstream_xianyu/main`
- Previously synced baseline: `8c1a1b1068744c0be2681f21d877f7b2c7c280eb`
- Previously synced summary: `2026-03-16 fix: 修复 Cherry Studio 图片流式兼容`
- Reviewed upstream head: `7f6d1572376e1232e52d043846bb454fda74db26`
- Reviewed head summary: `2026-03-24 fix(chat): 修复思考块图标连续旋转跳变`

### Upstream: chenyme/grok2api

- Remote name: `upstream_chenyme`
- Repository: `https://github.com/chenyme/grok2api`
- Synced reference branch: `upstream_chenyme/main`
- Previously synced baseline: `7796e080849b158514a40a5d62f0bec140e53842`
- Previously synced summary: `2026-03-17 Merge pull request #344 from chenyme/fix_cffi`
- Reviewed upstream head: `16e37b10a4b5ea5d7b6c216c2f6a9bda91f90971`
- Reviewed head summary: `2026-03-23 Merge pull request #374 from JinchengGao-Infty/fix-image-gen-app-chat`

## What was included in the previous full sync window

上一次整包同步最终落地到本地 `main@1479d0076169b618b0295aa8378f2bbc6eff288d`，主要包含：

- 先前已合入的一批上游后端更新（token / reverse / assets / model / response 相关）
- xianyu 的多图参考视频能力完整移植：
  - backend / API chain
  - public video API session plumbing
  - video workbench frontend (`video.html` / `video.js` / `video.css`)

## Previous selective sync decision window (reviewed on 2026-03-19)

本轮没有做整包 upstream merge，而是对两个上游在上述 baseline 之后的新提交做了逐条审阅，并只吸收最小高价值补丁。

### Selected from xianyu

- `4467a60298e44c355307a79fd36cd29a4ad1abce`
  - `fix: 修复 media_post 的 KeyError 日志冲突及 video 401 自动换 token`
  - 实际吸收内容：
    - `app/services/grok/services/video.py`：视频流式首包 401 自动换 token
    - `app/services/reverse/media_post.py`：日志格式修复

- `7f4b1dcd752f405a9a1cf6d34e4b60fa7f55a3d8`
  - `fix: 修复 URL 模式历史视频预览解析`
  - 实际吸收内容：
    - `app/static/public/js/video.js`：历史视频 / URL 模式预览解析修复

### Selected from chenyme

- `635e6e3524c5f54f26cd693b8bf42d64f031503b` (partial)
  - `chore: update version to 1.6.2 and adjust related file references`
  - 实际吸收内容：
    - `app/core/storage.py`：空 token 快照防覆盖保护（LocalStorage / RedisStorage / SQLStorage）
  - 明确未吸收内容：
    - 版本号更新
    - `uv.lock`
    - `_public` 静态页面与引用变更

### Selected minimal subset from xianyu `d35f717`

- `d35f71721cd1b7b7a92c339a892ded4fe63c29fb`
  - `fix: 修复4.20模型对话错误和注入提示词以支持openclaw调用工具`
  - 仅吸收最小兼容子集：
    - `app/api/v1/chat.py`：放宽 assistant/tool content 校验
    - `app/services/grok/utils/tool_call.py`：保留 tool role，不再压平成 user 文本
  - 明确未吸收内容：
    - `app_traffic.log` 落盘
    - few-shot / tool prompt 强化注入
    - `headers.py` 大改
    - `customPersonality`

### Explicitly skipped in this review window

- xianyu `69a3c6ad3d12b06d9a6c5a0c8de2b9e50713695d`
  - `style: 优化 token 列表 UI 布局，分页移至顶部，重构移动端批量操作浮窗`
  - 原因：管理后台 UI 改动，收益低于同步成本

- xianyu `d35f71721cd1b7b7a92c339a892ded4fe63c29fb` 的其余部分
  - 原因：侵入面过大，回归风险高

- chenyme `936efd78039df1a954e3d153de4ea6bb7dcc52e7` / `26f6d41df725394fa1548e358226195d714f9a7c`
  - `get_tokens` import 修复
  - 原因：本地路径为 `app/api/v1/admin_api/token.py`，不能直接套用，且当前价值有限

## Current selective sync decision window (reviewed on 2026-03-24)

本轮继续按“已审阅 head 之后的增量”逐条筛选，只吸收高价值、小范围补丁。

### Selected from xianyu

- `78cb981471636555c380295d3c2cb0d92cb44c4f`
  - `fix: 修复本地配置 TOML 序列化`
  - 实际吸收内容：
    - `app/core/storage.py`：本地配置 TOML 安全序列化（key quoting / string escaping / list/dict/None formatting）

### Selected from chenyme

- `fb95e1ab27a192f26daeaec84d39def26acad22c`
  - `fix: use app-chat REST API as primary image generation method, fallback to ws_imagine`
  - 实际吸收内容：
    - `app/services/grok/services/image.py`：图片生成主路径切换到 app-chat REST，ws_imagine 仅 fallback
    - `app/services/grok/services/chat.py`：`request_overrides` 透传
    - `app/services/reverse/app_chat.py`：支持 `request_overrides`

- `549c3dcae62698318bc3a4fddeb3933741444173`
  - `fix: refactor image edit to use file_attachments, improve error logging, extract markdown images`
  - 实际吸收内容：
    - `app/services/grok/services/image_edit.py`：普通图片编辑主路径切到 `file_attachments`
    - `app/api/v1/chat.py`：支持从 markdown 文本提取并去重图片 URL
    - `app/services/reverse/app_chat.py`：非 200 响应 body 读取与日志增强

### Explicitly skipped in this review window

- xianyu `83ae47d...`
  - 4.20 / 模型池 / admin config / UI 面过大，回归风险高

- xianyu 其余 chat/UI/NSFW 体验类提交
  - 原因：以体验打磨为主，不适合当前 selective sync

- chenyme `33caf94...`
  - 健康检查日志配置，当前价值低于同步成本

- chenyme `674add4...`
  - 图片提取辅助逻辑，当前已被 `549c3dc` 的主路径收益覆盖，暂不单独吸收

## How to use this next time

下次再同步时，先执行：

```bash
git fetch upstream_xianyu upstream_chenyme
```

下次再同步时，默认从“本次已经审阅到的 upstream head”之后继续检查，避免重复审查本文件中已经明确跳过或部分吸收的提交。

然后只检查以下两个范围之后的新提交：

### Xianyu incremental range

```bash
git log --oneline 7f6d1572376e1232e52d043846bb454fda74db26..upstream_xianyu/main
git diff --stat 7f6d1572376e1232e52d043846bb454fda74db26..upstream_xianyu/main
```

### Chenyme incremental range

```bash
git log --oneline 16e37b10a4b5ea5d7b6c216c2f6a9bda91f90971..upstream_chenyme/main
git diff --stat 16e37b10a4b5ea5d7b6c216c2f6a9bda91f90971..upstream_chenyme/main
```

## Update rule

每次完成一轮新的 upstream 同步后，务必同步更新本文件中的：

1. 本地落地 commit
2. 两个 upstream 的“已审阅 head”
3. 本轮实际吸收的 commit / 子集
4. 明确跳过的 commit 与原因

这样下一轮就可以直接从记录的 SHA 往后查，而不需要重新全量回看历史，也不会重复审查已经明确跳过的提交。
