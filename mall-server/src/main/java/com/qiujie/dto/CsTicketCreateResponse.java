package com.qiujie.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * 内部建单响应 — 只回对外工单号，不外泄自增主键
 *
 * @author qiujie
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "内部建单响应")
public class CsTicketCreateResponse {

    @Schema(description = "工单号，格式 TK-YYYYMMDD-xxxxxx")
    private String ticketNo;

    @Schema(description = "工单类型描述")
    private String category;

    @Schema(description = "工单状态描述")
    private String status;

    @Schema(description = "创建时间")
    private LocalDateTime createTime;
}
