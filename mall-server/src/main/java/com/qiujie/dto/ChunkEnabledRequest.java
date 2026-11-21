package com.qiujie.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 启停单块请求。
 *
 * @author qiujie
 */
@Data
@Schema(description = "启停切片")
public class ChunkEnabledRequest {

    @NotNull(message = "enabled 不能为空")
    @Schema(description = "是否启用")
    private Boolean enabled;
}
