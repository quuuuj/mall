package com.qiujie.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 内部建单请求（仅供 mall-customer 通过共享密钥调用）
 *
 * @author qiujie
 */
@Data
@Schema(description = "内部建单请求")
public class TicketCreateRequest {

    @NotNull(message = "用户 ID 不能为空")
    @Schema(description = "诉求所属用户 ID")
    private Integer userId;

    @NotNull(message = "会话 ID 不能为空")
    @Schema(description = "触发建单的客服会话 ID")
    private Long sessionId;

    @NotNull(message = "工单类型不能为空")
    @Schema(description = "工单类型: 1 退款退货 / 2 物流异常 / 3 发票 / 4 投诉建议")
    private Integer category;

    @Schema(description = "优先级: 1 低 / 2 中 / 3 高；不传按类型取默认值")
    private Integer priority;

    @NotBlank(message = "工单摘要不能为空")
    @Size(max = 200, message = "工单摘要不能超过 200 字符")
    @Schema(description = "一句话摘要")
    private String summary;

    @Schema(description = "结构化字段 JSON，四类工单各自的必填字段")
    private String detail;

    @Schema(description = "是否仍缺字段: 1 是 / 0 否；两轮追问后仍缺字段时置 1")
    private Integer needsInfo;
}
