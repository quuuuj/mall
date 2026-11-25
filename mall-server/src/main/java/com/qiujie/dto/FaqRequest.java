package com.qiujie.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * FAQ 新增/编辑请求。
 *
 * @author qiujie
 */
@Data
@Schema(description = "FAQ 新增/编辑请求")
public class FaqRequest {

    @NotBlank(message = "问题不能为空")
    @Schema(description = "标准问题")
    private String question;

    @NotBlank(message = "答案不能为空")
    @Schema(description = "标准答案")
    private String answer;

    @Schema(description = "分类")
    private String category;

    @Schema(description = "标签，逗号分隔")
    private String tags;

    @Schema(description = "是否启用，默认 1")
    private Integer enabled;
}
