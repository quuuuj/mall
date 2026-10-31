package com.qiujie.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.qiujie.enums.CsTicketCategoryEnum;
import com.qiujie.enums.CsTicketPriorityEnum;
import com.qiujie.enums.CsTicketStatusEnum;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

/**
 * 客服工单
 * <p>
 * 建单写入 cs_ticket，状态流转写 cs_ticket_log。对外只暴露 {@link #ticketNo}，
 * 内部自增主键不外泄。
 *
 * @author qiujie
 */
@Data
@Accessors(chain = true)
@TableName("cs_ticket")
public class CsTicket {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /**
     * 对外工单号，格式 TK-YYYYMMDD-xxxxxx（6 位大写十六进制），唯一索引
     */
    @TableField("ticket_no")
    private String ticketNo;

    @TableField("user_id")
    private Integer userId;

    /**
     * 触发建单的客服会话（cs_session.id）；由 Java 侧在建单时绑定
     */
    @TableField("session_id")
    private Long sessionId;

    @TableField("category")
    private CsTicketCategoryEnum category;

    @TableField("status")
    private CsTicketStatusEnum status;

    @TableField("priority")
    private CsTicketPriorityEnum priority;

    /**
     * 一句话摘要
     */
    @TableField("summary")
    private String summary;

    /**
     * 结构化字段 JSON（四类工单各自的必填字段）
     */
    @TableField("detail")
    private String detail;

    /**
     * 管理员备注
     */
    @TableField("admin_remark")
    private String adminRemark;

    /**
     * 追问两轮仍缺字段时为 1，不是状态
     */
    @TableField("needs_info")
    private Integer needsInfo;

    /**
     * 首次响应时间（管理员首次受理）
     */
    @TableField("first_response_time")
    private LocalDateTime firstResponseTime;

    /**
     * 标记解决时间
     */
    @TableField("resolved_time")
    private LocalDateTime resolvedTime;

    /**
     * 关闭时间
     */
    @TableField("closed_time")
    private LocalDateTime closedTime;

    @TableField("create_time")
    private LocalDateTime createTime;

    @TableField("update_time")
    private LocalDateTime updateTime;
}
