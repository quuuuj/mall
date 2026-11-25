package com.qiujie.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.qiujie.enums.TicketStatusEnum;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

/**
 * 客服工单状态变更日志
 * <p>
 * 每次状态流转写一条，记录操作人、变更前后状态、备注，用于追溯。
 *
 * @author qiujie
 */
@Data
@Accessors(chain = true)
@TableName("cs_ticket_log")
public class TicketLog {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("ticket_id")
    private Long ticketId;

    /**
     * 操作人用户 ID；用户本人操作时为该用户 ID，管理员操作时为管理员 ID，
     * 系统自动流转（如定时任务）约定为 0
     */
    @TableField("operator_id")
    private Integer operatorId;

    /**
     * 变更前状态；建单时为 null
     */
    @TableField("from_status")
    private TicketStatusEnum fromStatus;

    @TableField("to_status")
    private TicketStatusEnum toStatus;

    @TableField("remark")
    private String remark;

    @TableField("create_time")
    private LocalDateTime createTime;
}
