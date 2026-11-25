package com.qiujie.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

/**
 * 客服 FAQ 标准问答对。
 *
 * @author qiujie
 */
@Data
@Accessors(chain = true)
@TableName("cs_faq")
public class Faq {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("question")
    private String question;

    @TableField("answer")
    private String answer;

    @TableField("category")
    private String category;

    /** 标签，逗号分隔 */
    @TableField("tags")
    private String tags;

    /** 0 停用 1 启用 */
    @TableField("enabled")
    private Integer enabled;

    @TableField("hit_count")
    private Long hitCount;

    @TableField("operator_id")
    private Integer operatorId;

    @TableField("create_time")
    private LocalDateTime createTime;

    @TableField("update_time")
    private LocalDateTime updateTime;
}
