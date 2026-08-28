# 缺口雷达

本区汇总课程页与专业工作区的建设缺口，只记录公开可展示的元数据、大纲索引与摘要，不收录私有资料原件。

!!! info "质量门禁与成熟度度量"
    当前统计已纳入 `content/jiangsu/courses/` 的课程页体系。遵循自动化质量门禁，未经过人工核验或缺少关键官方依据的页面封顶 `machine_ready` / `yellow`，确保不把未核验资料误标为已签发版本。

## 成熟度指标

<div class="zk-grid zk-grid-3">
  <div class="zk-stat-card">
    <div class="zk-stat-number">0</div>
    <div class="zk-stat-label">Red 阻断级缺口</div>
  </div>
  <div class="zk-stat-card">
    <div class="zk-stat-number">18</div>
    <div class="zk-stat-label">Yellow 待核验/待完善</div>
  </div>
  <div class="zk-stat-card">
    <div class="zk-stat-number">0</div>
    <div class="zk-stat-label">Green 已签发可发布</div>
  </div>
</div>

## 明细报告与协作

<div class="zk-grid zk-grid-2">
  <a href="page-maturity.md" class="zk-card">
    <div class="zk-card-header">
      <span class="zk-badge zk-badge-blue">自动化投影</span>
    </div>
    <div class="zk-card-title">课程成熟度全量明细报告</div>
    <p class="zk-card-desc">查看 18 门课程的代码、生命周期 (lifecycle)、完整度 (completeness) 及具体缺口原因。</p>
  </a>

  <a href="https://github.com/SuperCatQR/jiangsu-zikao-aio/issues?q=is%3Aissue%20is%3Aopen%20label%3Acourse-gap" class="zk-card">
    <div class="zk-card-header">
      <span class="zk-badge zk-badge-amber">Issue 联动</span>
    </div>
    <div class="zk-card-title">GitHub Course-Gap 任务看板</div>
    <p class="zk-card-desc">自动同步至 GitHub Issues 的课程缺口补全任务列表，支持逐条跟踪与修复闭环。</p>
  </a>
</div>

## 缺口补齐流程

<div class="zk-steps">
  <div class="zk-step-item">
    <div class="zk-step-num">01</div>
    <div class="zk-step-content">
      <div class="zk-step-title">按优先级定界（优先 P0 公共必考课）</div>
      <p class="zk-step-desc">优先处理 <code>15040</code>、<code>15043</code>、<code>15044</code>、<code>00023</code> 等全省通用公共课与高复用专业基础课。</p>
    </div>
  </div>
  <div class="zk-step-item">
    <div class="zk-step-num">02</div>
    <div class="zk-step-content">
      <div class="zk-step-title">官方来源与教材计划闭环</div>
      <p class="zk-step-desc">锁定江苏省教育考试院权威考纲文件及当期指定教材书号/作者/出版社，写入 <code>sources.md</code>。</p>
    </div>
  </div>
  <div class="zk-step-item">
    <div class="zk-step-num">03</div>
    <div class="zk-step-content">
      <div class="zk-step-title">构建考纲知识树与学习计划</div>
      <p class="zk-step-desc">基于官方大纲目录构建 <code>syllabus.md</code> 章节索引，并在 <code>plan.md</code> 形成循序渐进的阶段式学习计划。</p>
    </div>
  </div>
  <div class="zk-step-item">
    <div class="zk-step-num">04</div>
    <div class="zk-step-content">
      <div class="zk-step-title">练习与真题元数据归档</div>
      <p class="zk-step-desc">公开页面收录真题考期元数据与答题模板（<code>practice.md</code>），私有题库原件入 <code>materials://</code> 私仓。</p>
    </div>
  </div>
</div>
