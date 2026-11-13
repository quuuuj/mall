package com.qiujie.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.qiujie.dto.TicketCreateRequest;
import com.qiujie.dto.TicketCreateResponse;
import com.qiujie.dto.TicketDetail;
import com.qiujie.dto.TicketListItem;
import com.qiujie.dto.TicketStatusUpdateRequest;

/**
 * 客服工单服务 — 建单、状态流转、操作日志的唯一写入点
 *
 * @author qiujie
 */
public interface TicketService {

    /**
     * 建单：写入 cs_ticket 并同步写一条建单日志，事务内完成。
     *
     * @param request 建单请求（调用方已通过共享密钥鉴权）
     * @return 对外工单号等信息
     */
    TicketCreateResponse create(TicketCreateRequest request);

    /**
     * 管理端工单列表，按创建时间倒序。
     *
     * @param current  页码
     * @param size     每页条数
     * @param status   状态码，null 表示不限
     * @param category 类型码，null 表示不限
     * @param startTime 创建时间下界（yyyy-MM-dd 或 yyyy-MM-dd HH:mm:ss），null 表示不限
     * @param endTime   创建时间上界，只给日期时含当天全天
     */
    IPage<TicketListItem> list(Integer current, Integer size, Integer status, Integer category,
                                 String startTime, String endTime);

    /**
     * 管理端工单详情：工单字段 + 最近 10 条会话片段。
     *
     * @param ticketNo 对外工单号
     */
    TicketDetail detail(String ticketNo);

    /**
     * 管理端改状态：校验流转合法性，写状态变更日志；首次响应时间在此写入。
     *
     * @param ticketNo  对外工单号
     * @param request   目标状态与备注
     * @param operatorId 操作人（管理员 ID）
     */
    TicketDetail.TicketView updateStatus(String ticketNo, TicketStatusUpdateRequest request, Integer operatorId);

    /**
     * 管理端写备注（不影响状态，不写状态日志）。
     */
    void updateRemark(String ticketNo, String adminRemark);
}
