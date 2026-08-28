# 标准与工程规范

本区汇总全站公开治理规则与工程规范，面向读者与协作维护者。内部执行契约与门禁配置由 `ops/jiangsu/` 与自动化脚本保证。

!!! info "治理与质量保障体系"
    规范公开内容边界、私有资料引用隔离、课程页五页模型、状态机生命周期演进与自动化 CI 门禁检查。

## 标准体系一览

<div class="zk-grid zk-grid-3">
  <a href="content-standard.md" class="zk-card">
    <div class="zk-card-header">
      <span class="zk-badge zk-badge-blue">内容规范</span>
    </div>
    <div class="zk-card-title">公开内容标准</div>
    <p class="zk-card-desc">Markdown 排版、资料状态分类、章节大纲规范及学习计划制定粒度要求。</p>
  </a>

  <a href="materials-policy.md" class="zk-card">
    <div class="zk-card-header">
      <span class="zk-badge zk-badge-neutral">隐私隔离</span>
    </div>
    <div class="zk-card-title">materials:// 协议政策</div>
    <p class="zk-card-desc">私有原件引用边界、URI 命名规范、路径脱敏与版权合规隔离准则。</p>
  </a>

  <a href="course-pages-contract.md" class="zk-card">
    <div class="zk-card-header">
      <span class="zk-badge zk-badge-green">页面契约</span>
    </div>
    <div class="zk-card-title">课程页结构契约</div>
    <p class="zk-card-desc">规范课程子目录结构、Frontmatter 字段、必备 H1/H2 标题与读者路径。</p>
  </a>

  <a href="publish-gate-contract.md" class="zk-card">
    <div class="zk-card-header">
      <span class="zk-badge zk-badge-amber">质量闸门</span>
    </div>
    <div class="zk-card-title">发布闸门规范</div>
    <p class="zk-card-desc">定义 publishable 状态的自动化质量门限，杜绝未校对内容擅自标记发布。</p>
  </a>

  <a href="course-status.md" class="zk-card">
    <div class="zk-card-header">
      <span class="zk-badge zk-badge-blue">状态机</span>
    </div>
    <div class="zk-card-title">课程状态机定义</div>
    <p class="zk-card-desc">规范 lifecycle (draft / machine_ready / reviewed / publishable) 与 completeness 的映射演进。</p>
  </a>

  <a href="review-checklist.md" class="zk-card">
    <div class="zk-card-header">
      <span class="zk-badge zk-badge-green">核验清单</span>
    </div>
    <div class="zk-card-title">人工审核清单</div>
    <p class="zk-card-desc">教研人员对课程大纲、教材版本、真题解析进行人工复核的九项把关清单。</p>
  </a>

  <a href="source-link-monitor.md" class="zk-card">
    <div class="zk-card-header">
      <span class="zk-badge zk-badge-amber">链接监控</span>
    </div>
    <div class="zk-card-title">官方来源监控</div>
    <p class="zk-card-desc">针对江苏省考试院及主考高校来源链接的有效性探测与失效基线监控。</p>
  </a>
</div>

## 标准快速索引表

| 规范名称 | 适用范围 | 核心目标 | 详情入口 |
| :--- | :--- | :--- | :---: |
| **公开内容标准** | 全站 Markdown 文档 | 统一排版规范、资料状态字段与计划粒度 | [查阅文档](content-standard.md) |
| **materials:// 政策** | 私有资产引用 | 杜绝版权扫描件泄露，规范统一协议 URI | [查阅文档](materials-policy.md) |
| **课程页结构契约** | `courses/` 课程目录 | 保证每门课满足五页闭环与必备章节 | [查阅文档](course-pages-contract.md) |
| **发布闸门规范** | CI 自动化流程 | 硬门禁拦截不合格页面，封顶 machine_ready | [查阅文档](publish-gate-contract.md) |
| **课程状态机** | 全生命周期管理 | 明确 draft / machine_ready / reviewed 状态迁移 | [查阅文档](course-status.md) |
| **人工审核清单** | 教研审核流程 | 提供结构化复核表，完成人工签发 | [查阅文档](review-checklist.md) |
| **官方来源监控** | 自动化巡检 | 监控官方 URL 存活与文件变动 | [查阅文档](source-link-monitor.md) |
