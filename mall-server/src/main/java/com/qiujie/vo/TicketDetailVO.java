package com.qiujie.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 管理端工单详情 — 工单字段 + 最近会话片段（只读）
 *
 * @author qiujie
 */
@Data
@Schema(description = "管理端工单详情")
public class TicketDetailVO {

    @Schema(description = "工单字段")
    private TicketView ticket;

    @Schema(description = "最近 10 条会话片段，按时间正序")
    private java.util.List<MessageView> messages;

    @Data
    @Schema(description = "工单字段（详情视图）")
    public static class TicketView {

        @Schema(description = "对外工单号")
        private String ticketNo;

        @Schema(description = "提单用户 ID")
        private Integer userId;

        @Schema(description = "提单用户名称")
        private String userName;

        @Schema(description = "来源会话 ID")
        private Long sessionId;

        private Integer category;
        private String categoryText;
        private Integer status;
        private String statusText;
        private Integer priority;
        private String priorityText;

        @Schema(description = "一句话摘要")
        private String summary;

        @Schema(description = "结构化字段 JSON，四类工单各自的必填字段")
        private String detail;

        @Schema(description = "管理员备注")
        private String adminRemark;

        @Schema(description = "是否仍缺字段")
        private Boolean needsInfo;

        @Schema(description = "首次响应时间，未响应为空")
        private LocalDateTime firstResponseTime;

        @Schema(description = "标记解决时间")
        private LocalDateTime resolvedTime;

        @Schema(description = "关闭时间")
        private LocalDateTime closedTime;

        private LocalDateTime createTime;
        private LocalDateTime updateTime;
    }

    @Data
    @Schema(description = "会话片段")
    public static class MessageView {

        @Schema(description = "消息类型: user / assistant / system / ticket / admin")
        private String type;

        @Schema(description = "消息正文")
        private String content;

        private LocalDateTime createTime;
    }
}
