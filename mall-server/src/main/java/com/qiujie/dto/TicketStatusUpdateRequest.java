package com.qiujie.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 管理端工单状态流转请求
 *
 * @author qiujie
 */
@Data
@Schema(description = "工单状态流转请求")
public class TicketStatusUpdateRequest {

    @NotNull(message = "目标状态不能为空")
    @Schema(description = "目标状态: 0 待处理 / 1 处理中 / 2 已解决 / 3 已关闭")
    private Integer status;

    @Size(max = 500, message = "备注不能超过 500 字符")
    @Schema(description = "本次流转的备注")
    private String remark;
}
