package com.qiujie.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 文档元数据编辑请求。
 *
 * @author qiujie
 */
@Data
@Schema(description = "文档元数据编辑请求")
public class KnowledgeDocUpdateRequest {

    @Schema(description = "文档标题")
    private String title;

    @Schema(description = "分类")
    private String category;

    @Schema(description = "标签，逗号分隔")
    private String tags;

    @Schema(description = "分块字符数")
    private Integer chunkSize;

    @Schema(description = "分块重叠字符数")
    private Integer chunkOverlap;

    @Schema(description = "清洗规则开关 JSON")
    private String cleanRules;
}
