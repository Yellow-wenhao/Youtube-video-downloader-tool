# UI Refactor TODO

## Status

本文件已降级为设计与 legacy GUI 参考文档，不再承担当前产品路线的执行排期。

当前唯一有效的项目推进清单是：

- [AGENT_TODO.md](D:/YTBDLP/docs/AGENT_TODO.md)

## Why

仓库已经明确切到 Web-first：

- 主产品界面是 `app/web/`
- 桌面 GUI 是 legacy compatibility surface

因此，原先这份文档里“Phase 1/2/3/4/5”的执行顺序，不再代表当前项目真实优先级。

## What This File Is For Now

保留它，只为了三件事：

1. 回看早期桌面 GUI 重构时采用过的设计判断
2. 给 legacy GUI bugfix / 小幅 polish 提供参考
3. 给 Web UI 设计借鉴提供历史上下文，但不能直接当 TODO 执行

## Legacy Refactor Snapshot

已完成的历史方向：

- [x] 配置页围绕任务设置、输出和执行意图重构
- [x] 增加任务摘要区
- [x] 强化主次操作层级
- [x] 队列概览与状态过滤
- [x] 审核工具栏重组
- [x] 顶层导航键盘焦点恢复

仍未完成、但当前默认不执行的 legacy 项：

- [ ] 为 queue 卡片和 review 卡片补一致的 focus 样式
- [ ] 审查 config / queue / Agent 视图的 tab 顺序
- [ ] 在 legacy GUI 下验证 `125%` Windows 缩放和 `1366px` 宽度
- [ ] 给 queue / review / Agent 区补更丰富的 empty state
- [ ] 给 queue 和 review 操作补键盘快捷键
- [ ] 仅在提升状态清晰度时加入动画

## Rule

如果这里的某个事项重新变成当前优先工作，必须先完成下列动作之一：

1. 把它迁移到 [AGENT_TODO.md](D:/YTBDLP/docs/AGENT_TODO.md)
2. 明确标注为 legacy GUI 专项修复，并在提交中说明不影响 Web-first 默认路线

在此之前，本文件只提供参考，不提供排期。
