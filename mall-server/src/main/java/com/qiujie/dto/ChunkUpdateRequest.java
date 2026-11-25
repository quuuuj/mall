package com.qiujie.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * 编辑单块正文请求。
 *
 * @author qiujie
 */
@Data
@Schema(description = "编辑切片正文")
public class ChunkUpdateRequest {

    @NotBlank(message = "正文不能为空")
    @Schema(description = "正文")
    private String content;
}
