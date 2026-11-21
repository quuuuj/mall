package com.qiujie.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 知识库文档分块（Qdrant payload 投影，改动不落库）。
 *
 * @author qiujie
 */
@Data
@Schema(description = "知识库文档分块")
public class KnowledgeChunkVO {

    @Schema(description = "文档 ID")
    private Long docId;

    @Schema(description = "块序号")
    private Integer chunkIndex;

    @Schema(description = "正文")
    private String content;

    @Schema(description = "是否启用")
    private Boolean enabled;

    @Schema(description = "正文字数")
    private Integer contentLength;

    public void setContent(String content) {
        this.content = content;
        this.contentLength = content == null ? 0 : content.length();
    }
}
