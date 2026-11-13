<template>
  <div class="page-container">
    <!-- 搜索区 -->
    <el-card class="page-search" shadow="never">
      <el-form :inline="true" :model="query" size="small" class="page-search-form">
        <el-form-item label="状态" class="page-search-item">
          <el-select v-model="query.status" clearable placeholder="请选择状态" class="w-140px">
            <el-option v-for="item in statusOptions" :key="item.code" :label="item.text" :value="item.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型" class="page-search-item">
          <el-select v-model="query.category" clearable placeholder="请选择类型" class="w-140px">
            <el-option v-for="item in categoryOptions" :key="item.code" :label="item.text" :value="item.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围" class="page-search-item">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item class="page-search-action">
          <el-button type="primary" :icon="'Search'" @click="handleSearch">查询</el-button>
          <el-button :icon="'Refresh'" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 表格 -->
    <el-card class="page-table" shadow="never">
      <el-table :data="tableData" border v-loading="loading" height="calc(100vh - 400px)">
        <template #empty><el-empty description="暂无数据" /></template>
        <el-table-column prop="ticketNo" label="工单号" min-width="180" align="center" />
        <el-table-column prop="userName" label="用户" min-width="100" align="center">
          <template #default="{row}">{{ row.userName || row.userId }}</template>
        </el-table-column>
        <el-table-column prop="categoryText" label="类型" width="110" align="center" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{row}">
            <el-tag :type="statusTypes[row.status] || 'info'" size="small">{{ row.statusText }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="优先级" width="90" align="center">
          <template #default="{row}">
            <el-tag :type="priorityTypes[row.priority] || 'info'" size="small" effect="plain">{{ row.priorityText }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
        <el-table-column label="缺字段" width="90" align="center">
          <template #default="{row}">
            <el-tag v-if="row.needsInfo" type="warning" size="small">待补充</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="createTime" label="创建时间" width="180" align="center" />
        <el-table-column label="操作" width="100" align="center" fixed="right">
          <template #default="{row}">
            <el-button link type="primary" size="small" @click="handleDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="page-pagination">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          v-model:current-page="query.current"
          v-model:page-size="query.size"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="fetchData"
          @size-change="fetchData"
        />
      </div>
    </el-card>

    <!-- 详情弹窗 -->
    <el-dialog title="工单详情" v-model="detailVisible" width="860px" :close-on-click-modal="false">
      <el-descriptions :column="2" border class="mb-16px">
        <el-descriptions-item label="工单号">{{ ticket.ticketNo }}</el-descriptions-item>
        <el-descriptions-item label="用户">{{ ticket.userName || ticket.userId }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ ticket.categoryText }}</el-descriptions-item>
        <el-descriptions-item label="优先级">{{ ticket.priorityText }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusTypes[ticket.status] || 'info'" size="small">{{ ticket.statusText }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="会话 ID">{{ ticket.sessionId || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ ticket.createTime }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ ticket.updateTime }}</el-descriptions-item>
        <el-descriptions-item label="首次响应">{{ ticket.firstResponseTime || '-' }}</el-descriptions-item>
        <el-descriptions-item label="解决时间">{{ ticket.resolvedTime || '-' }}</el-descriptions-item>
        <el-descriptions-item label="关闭时间" :span="2">{{ ticket.closedTime || '-' }}</el-descriptions-item>
        <el-descriptions-item label="摘要" :span="2">{{ ticket.summary }}</el-descriptions-item>
      </el-descriptions>

      <h4 class="mb-8px text-14px font-600 text-#303133">诉求字段</h4>
      <el-descriptions v-if="detailEntries.length" :column="2" border size="small" class="mb-16px">
        <el-descriptions-item v-for="item in detailEntries" :key="item.key" :label="item.label">{{ item.value }}</el-descriptions-item>
      </el-descriptions>
      <div v-else class="mb-16px text-13px text-#909399">无结构化字段</div>

      <h4 class="mb-8px text-14px font-600 text-#303133">处理</h4>
      <div class="mb-12px flex items-center gap-8px">
        <el-button
          v-for="action in statusActions"
          :key="action.code"
          :type="action.type"
          size="small"
          :loading="statusLoading"
          @click="handleStatus(action)"
        >{{ action.label }}</el-button>
        <span v-if="!statusActions.length" class="text-13px text-#909399">已关闭，无可用操作</span>
      </div>
      <el-input
        v-model="remarkDraft"
        type="textarea"
        :rows="3"
        maxlength="500"
        show-word-limit
        placeholder="管理员备注，内部可见"
      />
      <div class="mt-8px flex justify-end">
        <el-button size="small" :loading="remarkLoading" @click="handleSaveRemark">保存备注</el-button>
      </div>

      <h4 class="mb-8px mt-16px text-14px font-600 text-#303133">最近会话片段</h4>
      <div v-if="messages.length" class="msg-list">
        <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.type">
          <span class="msg-role">{{ roleText(m.type) }}</span>
          <span class="msg-content">{{ m.content }}</span>
          <span class="msg-time">{{ m.createTime }}</span>
        </div>
      </div>
      <div v-else class="text-13px text-#909399">无会话记录</div>

      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as ticketApi from '@/api/ticket'

const statusOptions = [
  { code: 0, text: '待处理' },
  { code: 1, text: '处理中' },
  { code: 2, text: '已解决' },
  { code: 3, text: '已关闭' }
]
const categoryOptions = [
  { code: 1, text: '退款退货' },
  { code: 2, text: '物流异常' },
  { code: 3, text: '发票' },
  { code: 4, text: '投诉建议' }
]
const statusTypes = { 0: 'warning', 1: 'primary', 2: 'success', 3: 'info' }
const priorityTypes = { 1: 'info', 2: 'warning', 3: 'danger' }

// 与服务端 TicketStatusEnum 的流转表保持一致，前端只做展示，最终以服务端校验为准
const TRANSITIONS = {
  0: [1, 3],
  1: [2, 3],
  2: [3, 1],
  3: []
}
const ACTION_LABELS = {
  0: { 1: '受理', 2: '标记解决', 3: '关闭' },
  1: { 2: '标记解决', 3: '关闭' },
  2: { 3: '关闭', 1: '重新处理' }
}

const DETAIL_LABELS = {
  orderNo: '订单号',
  reason: '退款/退货原因',
  received: '是否已收货',
  phenomenon: '物流异常现象',
  title: '发票抬头',
  taxNo: '税号',
  description: '投诉内容'
}

const query = reactive({ current: 1, size: 10, status: null, category: null })
const dateRange = ref([])
const tableData = ref([])
const total = ref(0)
const loading = ref(false)

const detailVisible = ref(false)
const ticket = ref({})
const messages = ref([])
const remarkDraft = ref('')
const statusLoading = ref(false)
const remarkLoading = ref(false)

const statusActions = computed(() => {
  const targets = TRANSITIONS[ticket.value.status] || []
  return targets.map(code => ({
    code,
    label: ACTION_LABELS[ticket.value.status]?.[code] || actionText(code),
    type: code === 3 ? 'danger' : 'primary'
  }))
})

const detailEntries = computed(() => {
  const raw = ticket.value.detail
  if (!raw) return []
  let parsed
  try {
    parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch {
    return [{ key: 'detail', label: '原始内容', value: raw }]
  }
  if (!parsed || typeof parsed !== 'object') return [{ key: 'detail', label: '原始内容', value: String(raw) }]
  return Object.entries(parsed)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => ({
      key: k,
      label: DETAIL_LABELS[k] || k,
      value: typeof v === 'boolean' ? (v ? '是' : '否') : String(v)
    }))
})

function actionText(code) {
  return statusOptions.find(o => o.code === code)?.text || ''
}

function roleText(type) {
  return { user: '用户', assistant: '智能客服', admin: '人工客服', system: '系统', ticket: '工单' }[type] || type
}

async function fetchData() {
  loading.value = true
  try {
    const params = { current: query.current, size: query.size }
    if (query.status !== null && query.status !== '') params.status = query.status
    if (query.category !== null && query.category !== '') params.category = query.category
    if (dateRange.value?.length === 2) {
      params.startTime = dateRange.value[0]
      params.endTime = dateRange.value[1]
    }
    const res = await ticketApi.list(params)
    tableData.value = res.data.records || []
    total.value = res.data.total || 0
  } catch (e) {
    ElMessage.error(typeof e === 'string' ? e : '加载工单失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  query.current = 1
  fetchData()
}

function handleReset() {
  query.status = null
  query.category = null
  dateRange.value = []
  query.current = 1
  fetchData()
}

async function handleDetail(row) {
  try {
    const res = await ticketApi.detail(row.ticketNo)
    ticket.value = res.data.ticket || {}
    messages.value = res.data.messages || []
    remarkDraft.value = ticket.value.adminRemark || ''
    detailVisible.value = true
  } catch (e) {
    ElMessage.error(typeof e === 'string' ? e : '加载工单详情失败')
  }
}

async function handleStatus(action) {
  try {
    await ElMessageBox.confirm(`确认将工单 ${ticket.value.ticketNo} 变更为「${actionText(action.code)}」？`, '提示', { type: 'warning' })
  } catch { return }
  statusLoading.value = true
  try {
    const res = await ticketApi.updateStatus(ticket.value.ticketNo, { status: action.code })
    ticket.value = { ...ticket.value, ...(res.data || {}) }
    ElMessage.success('状态已更新')
    fetchData()
  } catch (e) {
    ElMessage.error(typeof e === 'string' ? e : '状态更新失败')
  } finally {
    statusLoading.value = false
  }
}

async function handleSaveRemark() {
  remarkLoading.value = true
  try {
    await ticketApi.updateRemark(ticket.value.ticketNo, remarkDraft.value)
    ticket.value = { ...ticket.value, adminRemark: remarkDraft.value }
    ElMessage.success('备注已保存')
    fetchData()
  } catch (e) {
    ElMessage.error(typeof e === 'string' ? e : '备注保存失败')
  } finally {
    remarkLoading.value = false
  }
}

onMounted(fetchData)
</script>

<style lang="scss" scoped>
.msg-list {
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 12px;
  background: #fbfbfc;
}

.msg-row {
  display: flex;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  line-height: 1.6;
  border-bottom: 1px dashed #ebeef5;

  &:last-child { border-bottom: none; }

  &.user .msg-role { color: #303133; }
  &.assistant .msg-role { color: #a10000; }
  &.admin .msg-role { color: #409eff; }
}

.msg-role {
  flex-shrink: 0;
  width: 64px;
  color: #909399;
}

.msg-content {
  flex: 1;
  color: #606266;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-time {
  flex-shrink: 0;
  color: #c0c4cc;
  font-size: 12px;
}
</style>
