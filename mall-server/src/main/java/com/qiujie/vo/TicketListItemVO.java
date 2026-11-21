package com.qiujie.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 管理端工单列表项。
 * <p>
 * 只暴露对外工单号，不带自增主键；类型/状态/优先级同时给出码值与文案，
 * 前端不必再维护一份字典。
 *
 * @author qiujie
 */
@Data
@Schema(description = "管理端工单列表项")
public class TicketListItemVO {

    @Schema(description = "对外工单号")
    private String ticketNo;

    @Schema(description = "提单用户 ID")
    private Integer userId;

    @Schema(description = "提单用户名称")
    private String userName;

    @Schema(description = "类型码: 1 退款退货 / 2 物流异常 / 3 发票 / 4 投诉建议")
    private Integer category;

    @Schema(description = "类型文案")
    private String categoryText;

    @Schema(description = "状态码: 0 待处理 / 1 处理中 / 2 已解决 / 3 已关闭")
    private Integer status;

    @Schema(description = "状态文案")
    private String statusText;

    @Schema(description = "优先级码: 1 低 / 2 中 / 3 高")
    private Integer priority;

    @Schema(description = "优先级文案")
    private String priorityText;

    @Schema(description = "一句话摘要")
    private String summary;

    @Schema(description = "是否仍缺字段")
    private Boolean needsInfo;

    @Schema(description = "创建时间")
    private LocalDateTime createTime;
}
