package com.qiujie.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/**
 * 管理端工单备注请求
 *
 * @author qiujie
 */
@Data
@Schema(description = "工单备注请求")
public class TicketRemarkRequest {

    @NotBlank(message = "备注不能为空")
    @Size(max = 500, message = "备注不能超过 500 字符")
    @Schema(description = "管理员备注")
    private String adminRemark;
}
