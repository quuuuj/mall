package com.qiujie.service;

import com.qiujie.dto.CsTicketCreateRequest;
import com.qiujie.dto.CsTicketCreateResponse;

/**
 * 客服工单服务 — 建单、状态流转、操作日志的唯一写入点
 *
 * @author qiujie
 */
public interface CsTicketService {

    /**
     * 建单：写入 cs_ticket 并同步写一条建单日志，事务内完成。
     *
     * @param request 建单请求（调用方已通过共享密钥鉴权）
     * @return 对外工单号等信息
     */
    CsTicketCreateResponse create(CsTicketCreateRequest request);
}
