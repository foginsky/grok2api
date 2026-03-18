# Upstream Sync Baselines

用于记录本仓库每次同步上游时所依据的基线提交，方便下次只检查这些基线之后的新变化，减少重复比对工作量。

## Current recorded baseline

记录时间：2026-03-18

### Local fork landing point

- Repository: `git@github-account-b:foginsky/grok2api.git`
- Branch: `main`
- Synced local commit: `1479d0076169b618b0295aa8378f2bbc6eff288d`
- Commit summary: `2026-03-18 feat(video): add multi-reference video workflow`

### Upstream: XianYuDaXian/grok2api

- Remote name: `upstream_xianyu`
- Repository: `https://github.com/XianYuDaXian/grok2api`
- Synced reference branch: `upstream_xianyu/main`
- Recorded upstream commit: `8c1a1b1068744c0be2681f21d877f7b2c7c280eb`
- Commit summary: `2026-03-16 fix: 修复 Cherry Studio 图片流式兼容`

### Upstream: chenyme/grok2api

- Remote name: `upstream_chenyme`
- Repository: `https://github.com/chenyme/grok2api`
- Synced reference branch: `upstream_chenyme/main`
- Recorded upstream commit: `7796e080849b158514a40a5d62f0bec140e53842`
- Commit summary: `2026-03-17 Merge pull request #344 from chenyme/fix_cffi`

## What was included in this sync window

本轮同步最终落地到本地 `main@1479d0076169b618b0295aa8378f2bbc6eff288d`，主要包含：

- 先前已合入的一批上游后端更新（token / reverse / assets / model / response 相关）
- xianyu 的多图参考视频能力完整移植：
  - backend / API chain
  - public video API session plumbing
  - video workbench frontend (`video.html` / `video.js` / `video.css`)

## How to use this next time

下次再同步时，先执行：

```bash
git fetch upstream_xianyu upstream_chenyme
```

然后只检查以下两个范围之后的新提交：

### Xianyu incremental range

```bash
git log --oneline 8c1a1b1068744c0be2681f21d877f7b2c7c280eb..upstream_xianyu/main
git diff --stat 8c1a1b1068744c0be2681f21d877f7b2c7c280eb..upstream_xianyu/main
```

### Chenyme incremental range

```bash
git log --oneline 7796e080849b158514a40a5d62f0bec140e53842..upstream_chenyme/main
git diff --stat 7796e080849b158514a40a5d62f0bec140e53842..upstream_chenyme/main
```

## Update rule

每次完成一轮新的 upstream 同步后，务必同步更新本文件中的：

1. 本地落地 commit
2. `upstream_xianyu` 基线 commit
3. `upstream_chenyme` 基线 commit
4. 本轮纳入的主要变化摘要

这样下一轮就可以直接从记录的 SHA 往后查，而不需要重新全量回看历史。
