# Agent TODO

本文档是当前项目的单一执行清单，用来回答三件事：

1. 项目现在做到哪一步了
2. 下一步最合理的动作是什么
3. 在对话丢失时，默认应从哪里继续

约定：

- `docs/AGENT_TODO.md`
  - 唯一执行清单
- `docs/AGENT_IMPLEMENTATION_PLAN.md`
  - 架构参考，不承担实时 TODO 职责
- `docs/WEB_WORKSPACE_REGRESSION_CHECKLIST.md`
  - Web 工作台专项回归清单

执行规则：

- 默认从上到下处理第一个未完成的 `P0 / P1 / P2` 事项
- 每完成一项，都同步更新勾选状态和验证记录
- 优先把新需求归到现有条目下，避免平行计划继续膨胀

---

## A. 当前基线（已完成）

- [x] Web-first 已成为默认产品方向，GUI 只保留为 legacy compatibility path
- [x] `app/core/`、`app/tools/`、`app/agent/`、`app/web/` 主体结构已收口
- [x] Web 工作台主链路可跑通：创建任务、审核候选、确认下载、查看结果、重试失败项
- [x] Agent runtime 已迁移到 LangGraph 主执行路径，`AgentRunner` 保留为 facade
- [x] Web 生命周期接口已暴露更清晰的 execution insight、失败恢复动作和本地 graph debug 入口
- [x] 统一解释器回归已覆盖 `/api/agent/plan`、`/api/agent/run`、`/api/agent/resume`、workspace lifecycle/poll

验证：

- `tests/test_langgraph_runtime.py`
- `tests/test_web_agent_runtime_api.py`
- `tests/test_web_workspace_state.py`
- `tests/test_planner_error_mapping.py`

---

## B. P0 文档与发布收口（已完成）

目标：

- 清理编码问题，保证核心文档统一为 UTF-8
- 统一版本治理与 release / changelog 流程
- 再压缩一轮迁移期历史痕迹

TODO：

- [x] 修复 `README.md`、`docs/WINDOWS_RELEASE.md`、`docs/AGENT_TODO.md` 的编码一致性问题
- [x] 引入仓库级 `VERSION` 文件，作为当前版本基线
- [x] 让 Python 入口与 release workflow 默认读取 `VERSION`
- [x] 更新 `CHANGELOG.md`，补齐 `0.1.4` 发布记录
- [x] 为历史迁移文档补统一的“历史参考”状态说明
- [x] 清理仍会误导当前路线的旧 TODO / 迁移表述

验证：

- `README.md`、`docs/WINDOWS_RELEASE.md`、`docs/AGENT_TODO.md` 可直接以 UTF-8 打开
- `.github/workflows/windows-release.yml` 会校验 tag 与 `VERSION` 一致
- `scripts/build_windows_release.ps1` 默认从 `VERSION` 取版本

---

## C. P1 发布后整理

目标：

- 让发布流程从“可用”变成“更容易维护”

TODO：

- [x] 补一份更短的发布操作清单，适合每次发版时直接执行
- [x] 评估是否需要保留历史 release 产物，避免 `build/release/` 长期堆积
- [x] 检查 installer / launcher 的中文显示文本是否全部恢复为正常编码

验证：

- [docs/RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md)
- [docs/WINDOWS_RELEASE.md](./WINDOWS_RELEASE.md)
- `app/web/release_launcher.py`
- `packaging/windows/installer.iss`

---

## D. 下一步候选

如果当前没有新缺陷，默认继续做 `C` 里剩余两项。
