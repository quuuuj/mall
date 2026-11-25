package com.qiujie.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

/**
 * 知识库变更记录。
 *
 * @author qiujie
 */
@Data
@Accessors(chain = true)
@TableName("cs_knowledge_change_log")
public class KnowledgeChangeLog {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /** DOC / FAQ / CHUNK / REBUILD */
    @TableField("target_type")
    private String targetType;

    /** 对象 ID，重建时为 0 */
    @TableField("target_id")
    private Long targetId;

    /** CREATE/UPDATE/DELETE/TOGGLE/REBUILD/INGEST */
    @TableField("action")
    private String action;

    @TableField("detail")
    private String detail;

    @TableField("operator_id")
    private Integer operatorId;

    @TableField("create_time")
    private LocalDateTime createTime;
}
