import request from '@/utils/request'
const url = '/ticket'

export const list = (params) => request.get(url, { params })
export const detail = (ticketNo) => request.get(`${url}/${ticketNo}`)
export const updateStatus = (ticketNo, data) => request.put(`${url}/${ticketNo}/status`, data)
export const updateRemark = (ticketNo, adminRemark) => request.put(`${url}/${ticketNo}/remark`, { adminRemark })
