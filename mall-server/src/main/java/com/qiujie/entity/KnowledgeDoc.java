package com.qiujie.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

/**
 * 客服知识库文档。
 * <p>
 * 文档内容不存 DB：原文件落在上传目录，解析分块后的向量存 Qdrant。
 * 本表只存元数据、处理状态与处理参数。
 *
 * @author qiujie
 */
@Data
@Accessors(chain = true)
@TableName("cs_knowledge_doc")
public class KnowledgeDoc {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /** 存储文件名（上传目录内相对路径） */
    @TableField("file_name")
    private String fileName;

    /** 原始文件名 */
    @TableField("original_name")
    private String originalName;

    /** pdf/docx/md/txt/html/image */
    @TableField("file_type")
    private String fileType;

    @TableField("file_size")
    private Long fileSize;

    @TableField("title")
    private String title;

    @TableField("category")
    private String category;

    /** 标签，逗号分隔 */
    @TableField("tags")
    private String tags;

    /** 0 停用 1 启用 */
    @TableField("enabled")
    private Integer enabled;

    /** PENDING / PROCESSING / READY / FAILED */
    @TableField("status")
    private String status;

    /** 入库分块数 */
    @TableField("chunk_count")
    private Integer chunkCount;

    /** 失败原因 */
    @TableField("error_message")
    private String errorMessage;

    @TableField("chunk_size")
    private Integer chunkSize;

    @TableField("chunk_overlap")
    private Integer chunkOverlap;

    /** 清洗规则开关 JSON */
    @TableField("clean_rules")
    private String cleanRules;

    @TableField("operator_id")
    private Integer operatorId;

    @TableField("create_time")
    private LocalDateTime createTime;

    @TableField("update_time")
    private LocalDateTime updateTime;
}
