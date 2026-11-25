<template>
  <div class="page-container">
    <el-card class="page-search" shadow="never">
      <el-form :inline="true" :model="query" size="small" class="page-search-form">
        <el-form-item label="分类" class="page-search-item">
          <el-input v-model="query.category" placeholder="分类" clearable class="w-160px" />
        </el-form-item>
        <el-form-item label="标签" class="page-search-item">
          <el-input v-model="query.tags" placeholder="标签" clearable class="w-160px" />
        </el-form-item>
        <el-form-item label="状态" class="page-search-item">
          <el-select v-model="query.status" clearable placeholder="全部" class="w-140px">
            <el-option v-for="s in enumStore.getOptions('knowledgeStatus')" :key="s.code" :label="s.text" :value="s.code" />
          </el-select>
        </el-form-item>
        <el-form-item class="page-search-action">
          <el-button type="primary" :icon="'Search'" @click="handleSearch">查询</el-button>
          <el-button :icon="'Refresh'" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="page-table" shadow="never">
      <div class="page-table-actions">
        <div class="flex items-center gap-8px">
          <el-upload
            :action="uploadUrl"
            :headers="uploadHeaders"
            :with-credentials="true"
            :show-file-list="false"
            :on-success="onUploadSuccess"
            :on-error="onUploadError"
            accept=".pdf,.docx,.md,.txt,.html,.htm,.png,.jpg,.jpeg,.gif,.webp"
          >
            <el-button type="primary" :icon="'Upload'">上传文档</el-button>
          </el-upload>
          <el-button :icon="'Refresh'" :loading="rebuilding" @click="handleRebuild">重建向量</el-button>
        </div>
        <el-button link type="primary" @click="openLogs">变更记录</el-button>
      </div>

      <!-- 父行=文档，子行=切片；展开时按 docId 懒加载 -->
      <el-table :key="tableKey" :data="tableData" border v-loading="loading" height="calc(100vh - 430px)"
        :row-key="rowKey" lazy :load="loadChunks" :tree-props="{ children: 'children', hasChildren: 'hasChildren' }">
        <template #empty><el-empty description="暂无文档" /></template>
        <el-table-column label="标题 / 正文摘要" min-width="320" show-overflow-tooltip>
          <template #default="{row}">
            <template v-if="row.kind === 'chunk'">
              <span class="text-#909399">#{{ row.chunkIndex }}</span>
              <span class="ml-8px text-13px text-#606266">{{ row.content }}</span>
            </template>
            <template v-else>
              <span>{{ row.title || row.originalName }}</span>
              <span v-if="row.title && row.originalName" class="ml-8px text-12px text-#909399">{{ row.originalName }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{row}">
            <el-tag v-if="row.kind !== 'chunk'" :type="statusTypes[row.status] || 'info'" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="110" show-overflow-tooltip>
          <template #default="{row}">{{ row.kind === 'chunk' ? '' : row.category }}</template>
        </el-table-column>
        <el-table-column label="分块 / 字数" width="100" align="center">
          <template #default="{row}">{{ row.kind === 'chunk' ? row.contentLength : row.chunkCount }}</template>
        </el-table-column>
        <el-table-column label="启用" width="80" align="center">
          <template #default="{row}">
            <el-switch :model-value="row.kind === 'chunk' ? row.enabled : row.enabled === 1"
              @change="row.kind === 'chunk' ? handleToggleChunk(row, $event) : handleToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160" align="center">
          <template #default="{row}">{{ row.kind === 'chunk' ? '' : row.createTime }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" align="center" fixed="right">
          <template #default="{row}">
            <template v-if="row.kind === 'chunk'">
              <el-button link type="primary" size="small" @click="handleEditChunk(row)">编辑正文</el-button>
              <el-button link type="danger" size="small" @click="handleDeleteChunk(row)">删除</el-button>
            </template>
            <template v-else>
              <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
              <el-button link type="primary" size="small" @click="handlePreview(row)">原文</el-button>
              <el-button v-if="row.status === 'FAILED'" link type="warning" size="small" @click="handleRetry(row)">重试</el-button>
              <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
            </template>
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
          :page-sizes="[10, 20, 50]"
          @current-change="fetchData"
          @size-change="fetchData"
        />
      </div>
    </el-card>

    <!-- 编辑元数据与处理参数 -->
    <el-dialog title="编辑文档" v-model="editVisible" width="560px" :close-on-click-modal="false">
      <el-form :model="editForm" label-width="100px" size="small">
        <el-form-item label="标题"><el-input v-model="editForm.title" /></el-form-item>
        <el-form-item label="分类"><el-input v-model="editForm.category" /></el-form-item>
        <el-form-item label="标签"><el-input v-model="editForm.tags" placeholder="逗号分隔" /></el-form-item>
        <el-form-item label="分块大小">
          <el-input-number v-model="editForm.chunkSize" :min="100" :step="100" />
        </el-form-item>
        <el-form-item label="分块重叠">
          <el-input-number v-model="editForm.chunkOverlap" :min="0" :max="400" :step="10" />
        </el-form-item>
        <el-form-item label="清洗规则">
          <el-input v-model="editForm.cleanRules" type="textarea" :rows="5" placeholder='{"strip_header_footer": true}' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSaveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑切片正文：保存即重算向量 -->
    <el-dialog title="编辑切片正文" v-model="chunkEditVisible" width="720px" :close-on-click-modal="false">
      <div class="text-12px text-#909399 mb-8px">保存后立即重新计算向量并生效；重建向量、重试文档或切换文档启停会覆盖此处修改。</div>
      <el-input v-model="chunkEditForm.content" type="textarea" :rows="16" />
      <template #footer>
        <el-button @click="chunkEditVisible = false">取消</el-button>
        <el-button type="primary" :loading="chunkSaving" @click="handleSaveChunk">保存</el-button>
      </template>
    </el-dialog>

    <!-- 原文预览 -->
    <el-dialog title="文档原文" v-model="previewVisible" width="720px">
      <div class="text-13px text-#606266 whitespace-pre-wrap max-h-70vh overflow-auto">{{ previewContent }}</div>
    </el-dialog>

    <!-- 变更记录 -->
    <el-dialog title="变更记录" v-model="logVisible" width="860px">
      <el-table :data="logs" border size="small" max-height="60vh">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="targetType" label="对象" width="100" />
        <el-table-column prop="targetId" label="对象ID" width="100" />
        <el-table-column prop="action" label="动作" width="110" />
        <el-table-column prop="detail" label="详情" min-width="220" show-overflow-tooltip />
        <el-table-column prop="operatorId" label="操作人" width="90" />
        <el-table-column prop="createTime" label="时间" width="170" />
      </el-table>
      <div class="page-pagination">
        <el-pagination background layout="total, prev, pager, next" :total="logTotal"
          v-model:current-page="logQuery.current" @current-change="fetchLogs" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '@/api/knowledge'
import { useEnumStore } from '@/stores/modules/enum'

const enumStore = useEnumStore()
const statusTypes = { PENDING: 'info', PROCESSING: 'warning', READY: 'success', FAILED: 'danger' }
const statusText = (code) => enumStore.getLabel('knowledgeStatus', code)

const query = reactive({ current: 1, size: 10, category: '', tags: '', status: null })
const tableData = ref([])
const total = ref(0)
const loading = ref(false)
const rebuilding = ref(false)
// 切片增删改后重建表格，清掉 el-table 的懒加载子节点缓存
const tableKey = ref(0)

const editVisible = ref(false)
const saving = ref(false)
const editForm = reactive({ id: null, title: '', category: '', tags: '', chunkSize: 800, chunkOverlap: 100, cleanRules: '{}' })

const chunkEditVisible = ref(false)
const chunkSaving = ref(false)
const chunkEditForm = reactive({ docId: null, chunkIndex: null, content: '' })

const previewVisible = ref(false)
const previewContent = ref('')

const logVisible = ref(false)
const logs = ref([])
const logTotal = ref(0)
const logQuery = reactive({ current: 1, size: 10 })

// 后端走 Sa-Token Cookie 鉴权（axios withCredentials），el-upload 需显式带凭据
const uploadUrl = '/admin-api/knowledge/doc/upload'
const uploadHeaders = {}

const rowKey = (row) => row.kind === 'chunk'
  ? `c-${row.docId}-${row.chunkIndex}`
  : `d-${row.id}`

async function fetchData() {
  loading.value = true
  try {
    const res = await api.listDocs(query)
    tableData.value = (res.data.records || []).map(row => ({
      ...row, kind: 'doc', hasChildren: (row.chunkCount || 0) > 0
    }))
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

async function loadChunks(row, treeNode, resolve) {
  try {
    const res = await api.listChunks(row.id)
    const chunks = res.data || []
    if (chunks.length >= 1000) ElMessage.warning('切片超过 1000 条，仅显示前 1000 条')
    resolve(chunks.map(c => ({ ...c, kind: 'chunk' })))
  } catch (e) {
    resolve([])
  }
}

function handleSearch() { query.current = 1; fetchData() }
function handleReset() { query.category = ''; query.tags = ''; query.status = null; handleSearch() }

async function onUploadSuccess(res) {
  if (res.code !== 20000) { ElMessage.error(res.message || '上传失败'); return }
  ElMessage.success('已上传，正在后台解析入库')
  fetchData()
}
function onUploadError() { ElMessage.error('上传失败') }

async function handleRebuild() {
  await ElMessageBox.confirm('将清空向量并按启用文档全量重建，可能耗时数分钟；手工编辑过的切片会被覆盖，继续？', '提示', { type: 'warning' })
  rebuilding.value = true
  try {
    await api.rebuild()
    ElMessage.success('已触发重建')
  } finally {
    rebuilding.value = false
  }
}

function handleEdit(row) {
  Object.assign(editForm, {
    id: row.id, title: row.title, category: row.category, tags: row.tags,
    chunkSize: row.chunkSize, chunkOverlap: row.chunkOverlap, cleanRules: row.cleanRules
  })
  editVisible.value = true
}

async function handleSaveEdit() {
  saving.value = true
  try {
    const { id, ...data } = editForm
    await api.updateDoc(id, data)
    ElMessage.success('已保存（需重建向量生效）')
    editVisible.value = false
    fetchData()
  } finally {
    saving.value = false
  }
}

function handleEditChunk(row) {
  Object.assign(chunkEditForm, { docId: row.docId, chunkIndex: row.chunkIndex, content: row.content })
  chunkEditVisible.value = true
}

async function handleSaveChunk() {
  chunkSaving.value = true
  try {
    await api.updateChunk(chunkEditForm.docId, chunkEditForm.chunkIndex, { content: chunkEditForm.content })
    ElMessage.success('已保存，向量已更新')
    chunkEditVisible.value = false
    tableKey.value++
    fetchData()
  } finally {
    chunkSaving.value = false
  }
}

async function handleToggleChunk(row, val) {
  row.enabled = val
  try {
    await api.toggleChunk(row.docId, row.chunkIndex, val)
    ElMessage.success('已切换')
  } catch (e) {
    row.enabled = !val
  }
}

async function handleDeleteChunk(row) {
  await ElMessageBox.confirm(`确认删除切片 #${row.chunkIndex}？删除后序号不重排，重建向量会恢复该切片。`, '提示', { type: 'warning' })
  await api.deleteChunk(row.docId, row.chunkIndex)
  ElMessage.success('已删除')
  tableKey.value++
  fetchData()
}

async function handlePreview(row) {
  const res = await api.docDetail(row.id)
  previewContent.value = res.data.errorMessage || '原文预览需配置文件下载接口；当前展示处理信息。标题：' + res.data.title
  previewVisible.value = true
}

async function handleToggle(row) {
  await api.toggleDoc(row.id)
  ElMessage.success('已切换')
  fetchData()
}

async function handleRetry(row) {
  await api.retryDoc(row.id)
  ElMessage.success('已重新处理')
  fetchData()
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确认删除文档「${row.originalName}」？`, '提示', { type: 'warning' })
  await api.deleteDoc(row.id)
  ElMessage.success('已删除')
  fetchData()
}

async function fetchLogs() {
  const res = await api.changeLogs(logQuery)
  logs.value = res.data.records || []
  logTotal.value = res.data.total || 0
}
function openLogs() { logQuery.current = 1; fetchLogs() }

onMounted(() => { fetchData(); openLogs() })
</script>
