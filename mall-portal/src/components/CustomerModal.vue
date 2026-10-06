<template>
  <transition name="cs-panel">
    <div v-show="visible" class="cs-panel">
      <!-- 头部：头像 + 称呼 + 操作 -->
      <div class="hd">
        <div class="face">商</div>
        <div class="hd-text">
          <div class="name">小店助手</div>
          <div class="stat">在线 · 通常 1 分钟内回复</div>
        </div>
        <div class="acts">
          <button title="历史会话" @click="drawerOpen = true">☰</button>
          <button title="收起" @click="visible = false">
            <el-icon :size="15"><Minus /></el-icon>
          </button>
        </div>
      </div>

      <!-- 消息区 -->
      <div class="msgs" ref="msgListRef">
        <div v-if="messages.length === 0" class="welcome">
          <div class="hi">你好呀 <em>:)</em></div>
          <p>订单、物流、退换货，都可以直接问我</p>
          <div class="q">
            <span v-for="chip in quickChips" :key="chip" @click="quickAsk(chip)">{{ chip }}</span>
          </div>
        </div>

        <div
          v-for="(msg, index) in messages"
          :key="index"
          :class="['row', msg.type === 'user' ? 'u' : 'b']"
        >
          <div v-if="msg.type !== 'user'" class="av">AI</div>
          <div class="bb">{{ msg.content }}</div>
        </div>

        <!-- 流式输出中的回复 -->
        <div v-if="loading && currentStreamingText" class="row b">
          <div class="av">AI</div>
          <div class="bb streaming">{{ currentStreamingText }}</div>
        </div>
        <!-- 思考中 -->
        <div v-else-if="loading" class="row b">
          <div class="av">AI</div>
          <div class="bb">
            <span class="dots"><span></span><span></span><span></span></span>
          </div>
        </div>
      </div>

      <!-- 输入区：药丸框 -->
      <div class="ft">
        <div class="pill">
          <textarea
            v-model="inputMessage"
            placeholder="发消息…"
            :disabled="loading || !currentSessionId"
            @keydown.enter.exact.prevent="sendMessage"
          ></textarea>
          <button
            class="send"
            title="发送"
            :disabled="!inputMessage.trim() || loading || !currentSessionId"
            @click="sendMessage"
          >
            <el-icon :size="15"><Promotion /></el-icon>
          </button>
        </div>
      </div>

      <!-- 历史会话抽屉（底部上滑） -->
      <div class="drawer" :class="{ open: drawerOpen }" @click.self="drawerOpen = false">
        <div class="sheet">
          <div class="grab"></div>
          <div class="sh">
            <h3>历史会话</h3>
            <button class="new" @click="handleCreateSession">＋ 新会话</button>
          </div>
          <div class="list">
            <div
              v-for="s in sessions"
              :key="s.id"
              :class="['sh-item', { cur: currentSessionId === s.id }]"
              @click="selectSession(s.id); drawerOpen = false"
            >
              <div class="ci"><el-icon :size="15"><ChatDotRound /></el-icon></div>
              <div class="ti" :title="s.title">{{ s.title }}</div>
              <span class="del" @click.stop="handleDeleteSession(s.id)">×</span>
            </div>
            <div v-if="sessions.length === 0" class="empty">暂无历史对话</div>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { Minus, Promotion, ChatDotRound } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listCustomerSessions, createCustomerSession, deleteCustomerSession, listCustomerMessages } from '@/api/customer'

const visible = ref(false)
const drawerOpen = ref(false)
const sessions = ref([])
const currentSessionId = ref(null)
const messages = ref([])
const inputMessage = ref('')
const loading = ref(false)
const currentStreamingText = ref('')
const msgListRef = ref(null)

const quickChips = ['查订单', '问物流', '退换货', '优惠券']

const open = async () => {
  visible.value = true
  await loadSessions()
}

const loadSessions = async () => {
  try {
    const res = await listCustomerSessions()
    sessions.value = res.data || []
    if (sessions.value.length > 0) {
      if (!currentSessionId.value || !sessions.value.some(s => s.id === currentSessionId.value)) {
        await selectSession(sessions.value[0].id)
      } else {
        await selectSession(currentSessionId.value)
      }
    } else {
      await handleCreateSession()
    }
  } catch (err) {
    ElMessage.error(err.message || '加载会话列表失败')
  }
}

const selectSession = async (sessionId) => {
  currentSessionId.value = sessionId
  currentStreamingText.value = ''
  try {
    const res = await listCustomerMessages(sessionId)
    messages.value = res.data || []
    scrollToBottom()
  } catch (err) {
    ElMessage.error(err.message || '获取聊天记录失败')
  }
}

const handleCreateSession = async () => {
  try {
    const res = await createCustomerSession()
    const newSession = res.data
    sessions.value.unshift(newSession)
    await selectSession(newSession.id)
  } catch (err) {
    ElMessage.error(err.message || '创建会话失败')
  }
}

const handleDeleteSession = (sessionId) => {
  ElMessageBox.confirm('确定要删除该会话记录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await deleteCustomerSession(sessionId)
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
      if (currentSessionId.value === sessionId) {
        currentSessionId.value = null
        messages.value = []
        if (sessions.value.length > 0) {
          selectSession(sessions.value[0].id)
        } else {
          handleCreateSession()
        }
      }
      ElMessage.success('删除成功')
    } catch (err) {
      ElMessage.error(err.message || '删除失败')
    }
  }).catch(() => {})
}

const scrollToBottom = () => {
  nextTick(() => {
    if (msgListRef.value) {
      msgListRef.value.scrollTop = msgListRef.value.scrollHeight
    }
  })
}

const quickAsk = async (text) => {
  if (loading.value) return
  if (!currentSessionId.value) {
    await handleCreateSession()
    if (!currentSessionId.value) return
  }
  inputMessage.value = text
  sendMessage()
}

const sendMessage = async () => {
  const text = inputMessage.value.trim()
  if (!text || loading.value || !currentSessionId.value) return

  inputMessage.value = ''
  messages.value.push({ type: 'user', content: text })
  scrollToBottom()

  loading.value = true
  currentStreamingText.value = ''

  try {
    const response = await fetch('/portal-api/customer/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        sessionId: currentSessionId.value,
        message: text
      }),
      credentials: 'include'
    })

    if (!response.ok) {
      throw new Error(`请求失败: HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()

      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('data:')) {
          const data = trimmed.slice(5).trim()
          if (data === '[DONE]') {
            continue
          }
          currentStreamingText.value += data
          scrollToBottom()
        }
      }
    }

    if (currentStreamingText.value) {
      messages.value.push({
        type: 'assistant',
        content: currentStreamingText.value
      })
      currentStreamingText.value = ''
    }

    // 若会话标题为“新对话”，更新本地会话列表标题
    const s = sessions.value.find(item => item.id === currentSessionId.value)
    if (s && s.title === '新对话') {
      s.title = text.length > 20 ? text.substring(0, 20) + '...' : text
    }
  } catch (err) {
    ElMessage.error(err.message || '客服响应失败')
    messages.value.push({
      type: 'assistant',
      content: '抱歉，当前客服暂时无法响应，请稍后重试。'
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

defineExpose({
  open
})
</script>

<style scoped>
/* ============ 浮窗面板：原型 C · 导购伙伴 ============ */
.cs-panel {
  position: fixed;
  right: 70px;
  bottom: 24px;
  z-index: 100;
  width: 352px;
  height: 570px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 48px);
  border-radius: 18px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #fbfaf7;
  border: 1px solid #e7e3da;
  box-shadow: 0 20px 60px rgba(40, 38, 30, .18);
}

.cs-panel-enter-active, .cs-panel-leave-active {
  transition: opacity .25s ease, transform .25s ease;
}
.cs-panel-enter-from, .cs-panel-leave-to {
  opacity: 0;
  transform: translateY(16px) scale(.98);
}

/* 头部 */
.hd {
  padding: 16px 18px 14px;
  display: flex;
  align-items: center;
  gap: 11px;
  background: #fbfaf7;
  border-bottom: 1px solid #efece5;
  flex-shrink: 0;
}
.hd .face {
  width: 40px;
  height: 40px;
  border-radius: 14px;
  background: linear-gradient(135deg, #A10000, #d43d2a);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 15px;
  font-weight: 800;
  position: relative;
}
.hd .face::after {
  content: "";
  position: absolute;
  right: -2px;
  bottom: -2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #4ec984;
  border: 2px solid #fbfaf7;
}
.hd-text { flex: 1; min-width: 0; }
.hd .name { font-size: 14.5px; font-weight: 700; color: #2a2823; }
.hd .stat { margin-top: 2px; font-size: 11px; color: #9a9487; }
.hd .stat::before {
  content: "●";
  color: #4ec984;
  font-size: 8px;
  margin-right: 5px;
  vertical-align: 1px;
}
.hd .acts { display: flex; gap: 2px; }
.hd .acts button {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 9px;
  cursor: pointer;
  background: transparent;
  color: #8b857a;
  font-size: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.hd .acts button:hover { background: #f0ede5; color: #2a2823; }

/* 消息区：无框气泡 */
.msgs {
  flex: 1;
  overflow-y: auto;
  padding: 16px 16px 8px;
}
.welcome { padding-top: 56px; text-align: center; }
.welcome .hi { font-size: 20px; font-weight: 800; color: #2a2823; }
.welcome .hi em { font-style: normal; color: #A10000; }
.welcome p { margin-top: 8px; font-size: 12.5px; color: #9a9487; }
.welcome .q {
  margin-top: 22px;
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  justify-content: center;
}
.welcome .q span {
  padding: 7px 14px;
  font-size: 12px;
  cursor: pointer;
  background: #fff;
  border: 1px solid #e7e3da;
  border-radius: 20px;
  color: #6f6a5c;
  transition: all .15s;
}
.welcome .q span:hover {
  border-color: #A10000;
  color: #A10000;
  transform: translateY(-1px);
}

.row { display: flex; gap: 9px; margin-bottom: 15px; }
.row.u { flex-direction: row-reverse; }
.row.b .av {
  width: 30px;
  height: 30px;
  border-radius: 11px;
  flex-shrink: 0;
  background: linear-gradient(135deg, #A10000, #d43d2a);
  color: #fff;
  font-size: 9.5px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
}
.bb {
  max-width: 78%;
  font-size: 13.5px;
  line-height: 1.65;
  word-break: break-word;
  white-space: pre-wrap;
}
.row.b .bb { color: #33302a; padding: 2px 0; }
.row.u .bb {
  background: #191917;
  color: #f5f3ee;
  padding: 9px 14px;
  border-radius: 16px 16px 5px 16px;
}
.bb.streaming::after {
  content: "▌";
  color: #A10000;
  animation: cs-blink 1s infinite;
}
@keyframes cs-blink { 50% { opacity: 0; } }
.dots span {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 4px;
  background: #c9c2b4;
  border-radius: 50%;
  animation: cs-bounce 1.2s infinite;
}
.dots span:nth-child(2) { animation-delay: .15s; }
.dots span:nth-child(3) { animation-delay: .3s; }
@keyframes cs-bounce {
  0%, 60%, 100% { transform: none; }
  30% { transform: translateY(-4px); }
}

/* 输入：药丸框 */
.ft { padding: 10px 14px 14px; flex-shrink: 0; }
.ft .pill {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: #fff;
  border: 1px solid #e7e3da;
  border-radius: 22px;
  padding: 6px 6px 6px 16px;
  transition: border-color .15s, box-shadow .15s;
}
.ft .pill:focus-within {
  border-color: #c9c2b4;
  box-shadow: 0 4px 14px rgba(40, 38, 30, .08);
}
.ft textarea {
  flex: 1;
  resize: none;
  height: 34px;
  max-height: 90px;
  padding: 8px 0;
  border: none;
  outline: none;
  background: transparent;
  font: 13.5px/1.4 inherit;
  color: #2a2823;
}
.ft .send {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  flex-shrink: 0;
  background: #A10000;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform .15s, opacity .15s;
}
.ft .send:hover:not(:disabled) { transform: scale(1.08); }
.ft .send:disabled { opacity: .45; cursor: not-allowed; }

/* 历史抽屉（底部上滑） */
.drawer {
  position: absolute;
  inset: 0;
  z-index: 3;
  background: rgba(30, 28, 24, .25);
  opacity: 0;
  pointer-events: none;
  transition: opacity .2s;
}
.drawer.open { opacity: 1; pointer-events: auto; }
.drawer .sheet {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  max-height: 82%;
  background: #fbfaf7;
  border-radius: 18px 18px 0 0;
  transform: translateY(100%);
  transition: transform .28s ease;
  display: flex;
  flex-direction: column;
  box-shadow: 0 -8px 30px rgba(40, 38, 30, .15);
}
.drawer.open .sheet { transform: none; }
.sheet .grab {
  width: 36px;
  height: 4px;
  border-radius: 2px;
  background: #ddd8cd;
  margin: 10px auto 4px;
}
.sheet .sh {
  padding: 6px 18px 10px;
  display: flex;
  align-items: center;
}
.sheet .sh h3 { font-size: 14px; font-weight: 700; color: #2a2823; margin: 0; }
.sheet .sh .new {
  margin-left: auto;
  border: none;
  cursor: pointer;
  background: #191917;
  color: #fff;
  font: 600 11.5px/1 inherit;
  padding: 7px 13px;
  border-radius: 14px;
}
.sheet .sh .new:hover { background: #A10000; }
.sheet .list { overflow-y: auto; padding: 2px 12px 14px; }
.sh-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 11px;
  cursor: pointer;
}
.sh-item:hover { background: #f2efe8; }
.sh-item.cur { background: #fdf1f0; }
.sh-item .ci {
  width: 34px;
  height: 34px;
  border-radius: 11px;
  flex-shrink: 0;
  background: #efeadf;
  color: #8b857a;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sh-item.cur .ci { background: #f9ddd9; color: #A10000; }
.sh-item .ti {
  flex: 1;
  font-size: 13px;
  color: #3a3630;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sh-item.cur .ti { color: #A10000; font-weight: 600; }
.sh-item .del {
  color: #ccc6b8;
  font-size: 15px;
  padding: 3px;
  line-height: 1;
}
.sh-item .del:hover { color: #A10000; }
.empty {
  text-align: center;
  color: #9a9487;
  font-size: 12px;
  padding: 24px 0;
}
</style>
