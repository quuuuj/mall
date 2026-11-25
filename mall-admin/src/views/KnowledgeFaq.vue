<template>
  <div class="page-container">
    <el-card class="page-search" shadow="never">
      <el-form :inline="true" :model="query" size="small" class="page-search-form">
        <el-form-item label="分类" class="page-search-item">
          <el-input v-model="query.category" placeholder="分类" clearable class="w-160px" />
        </el-form-item>
        <el-form-item label="启用" class="page-search-item">
          <el-select v-model="query.enabled" clearable placeholder="全部" class="w-120px">
            <el-option label="启用" :value="1" />
            <el-option label="停用" :value="0" />
          </el-select>
        </el-form-item>
        <el-form-item class="page-search-action">
          <el-button type="primary" :icon="'Search'" @click="handleSearch">查询</el-button>
          <el-button :icon="'Refresh'" @click="handleReset">重置</el-button>
          <el-button type="success" :icon="'Plus'" @click="handleAdd">新增 FAQ</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="page-table" shadow="never">
      <el-table :data="tableData" border v-loading="loading" height="calc(100vh - 360px)">
        <template #empty><el-empty description="暂无 FAQ" /></template>
        <el-table-column prop="id" label="ID" width="80" align="center" />
        <el-table-column prop="question" label="标准问题" min-width="240" show-overflow-tooltip />
        <el-table-column prop="answer" label="标准答案" min-width="280" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="120" show-overflow-tooltip />
        <el-table-column prop="tags" label="标签" width="140" show-overflow-tooltip />
        <el-table-column prop="hitCount" label="命中" width="80" align="center" />
        <el-table-column label="启用" width="80" align="center">
          <template #default="{row}">
            <el-switch :model-value="row.enabled === 1" @change="handleToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center" fixed="right">
          <template #default="{row}">
            <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
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

    <el-dialog :title="editForm.id ? '编辑 FAQ' : '新增 FAQ'" v-model="editVisible" width="640px" :close-on-click-modal="false">
      <el-form :model="editForm" label-width="90px" size="small">
        <el-form-item label="标准问题" required>
          <el-input v-model="editForm.question" placeholder="用户最可能怎么问" />
        </el-form-item>
        <el-form-item label="标准答案" required>
          <el-input v-model="editForm.answer" type="textarea" :rows="6" placeholder="命中后直接返回给用户的内容" />
        </el-form-item>
        <el-form-item label="分类"><el-input v-model="editForm.category" /></el-form-item>
        <el-form-item label="标签"><el-input v-model="editForm.tags" placeholder="逗号分隔" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="editEnabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '@/api/knowledge'

const query = reactive({ current: 1, size: 10, category: '', enabled: null })
const tableData = ref([])
const total = ref(0)
const loading = ref(false)

const editVisible = ref(false)
const saving = ref(false)
const editForm = reactive({ id: null, question: '', answer: '', category: '', tags: '' })
const editEnabled = ref(true)

async function fetchData() {
  loading.value = true
  try {
    const res = await api.listFaqs(query)
    tableData.value = res.data.records || []
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}
function handleSearch() { query.current = 1; fetchData() }
function handleReset() { query.category = ''; query.enabled = null; handleSearch() }

function handleAdd() {
  Object.assign(editForm, { id: null, question: '', answer: '', category: '', tags: '' })
  editEnabled.value = true
  editVisible.value = true
}
function handleEdit(row) {
  Object.assign(editForm, {
    id: row.id, question: row.question, answer: row.answer,
    category: row.category, tags: row.tags
  })
  editEnabled.value = row.enabled === 1
  editVisible.value = true
}

async function handleSave() {
  if (!editForm.question?.trim() || !editForm.answer?.trim()) {
    ElMessage.warning('问题和答案不能为空')
    return
  }
  saving.value = true
  try {
    const data = {
      question: editForm.question, answer: editForm.answer,
      category: editForm.category, tags: editForm.tags, enabled: editEnabled.value ? 1 : 0
    }
    if (editForm.id) {
      await api.updateFaq(editForm.id, data)
      ElMessage.success('已保存')
    } else {
      await api.addFaq(data)
      ElMessage.success('已新增')
    }
    editVisible.value = false
    fetchData()
  } finally {
    saving.value = false
  }
}

async function handleToggle(row) {
  await api.toggleFaq(row.id)
  fetchData()
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确认删除 FAQ「${row.question}」？`, '提示', { type: 'warning' })
  await api.deleteFaq(row.id)
  ElMessage.success('已删除')
  fetchData()
}

onMounted(fetchData)
</script>
