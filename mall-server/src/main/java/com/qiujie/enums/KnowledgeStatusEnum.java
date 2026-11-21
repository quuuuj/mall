package com.qiujie.enums;

import com.baomidou.mybatisplus.annotation.EnumValue;
import com.fasterxml.jackson.annotation.JsonValue;
import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 知识库文档处理状态
 *
 * @author qiujie
 */
@Getter
@AllArgsConstructor
public enum KnowledgeStatusEnum implements DictEnum<String> {

    PENDING("PENDING", "待处理"),
    PROCESSING("PROCESSING", "处理中"),
    READY("READY", "就绪"),
    FAILED("FAILED", "失败");

    @JsonValue
    @EnumValue
    private final String code;
    private final String text;
}
