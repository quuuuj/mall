import request from '@/utils/request'
const url = '/knowledge'

// 文档
export const uploadDoc = (formData) => request.post(`${url}/doc/upload`, formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})
export const listDocs = (params) => request.get(`${url}/doc`, { params })
export const docDetail = (id) => request.get(`${url}/doc/${id}`)
export const updateDoc = (id, data) => request.put(`${url}/doc/${id}`, data)
export const deleteDoc = (id) => request.delete(`${url}/doc/${id}`)
export const toggleDoc = (id) => request.put(`${url}/doc/${id}/toggle`)
export const retryDoc = (id) => request.post(`${url}/doc/${id}/retry`)
export const rebuild = () => request.post(`${url}/rebuild`)
export const changeLogs = (params) => request.get(`${url}/change-log`, { params })

// 单块编辑（改动只落 Qdrant，重建会覆盖）
export const listChunks = (docId) => request.get(`${url}/doc/${docId}/chunks`)
export const updateChunk = (docId, chunkIndex, data) => request.put(`${url}/doc/${docId}/chunks/${chunkIndex}`, data)
export const toggleChunk = (docId, chunkIndex, enabled) => request.put(`${url}/doc/${docId}/chunks/${chunkIndex}/enabled`, { enabled })
export const deleteChunk = (docId, chunkIndex) => request.delete(`${url}/doc/${docId}/chunks/${chunkIndex}`)

// FAQ
export const listFaqs = (params) => request.get(`${url}/faq`, { params })
export const faqDetail = (id) => request.get(`${url}/faq/${id}`)
export const addFaq = (data) => request.post(`${url}/faq`, data)
export const updateFaq = (id, data) => request.put(`${url}/faq/${id}`, data)
export const deleteFaq = (id) => request.delete(`${url}/faq/${id}`)
export const toggleFaq = (id) => request.put(`${url}/faq/${id}/toggle`)

// 检索测试
export const testRetrieval = (data) => request.post(`${url}/test`, data)
export const testHistory = (params) => request.get(`${url}/test/history`, { params })
