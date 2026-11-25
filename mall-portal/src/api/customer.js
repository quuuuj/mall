import request from '@/utils/request'

export const listCustomerSessions = () => request.get('/customer')

export const createCustomerSession = () => request.post('/customer')

export const deleteCustomerSession = (id) => request.delete(`/customer/${id}`)

export const listCustomerMessages = (sessionId) => request.get(`/customer/${sessionId}/messages`)
