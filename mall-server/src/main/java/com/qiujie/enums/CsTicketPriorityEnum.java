package com.qiujie.enums;

import com.baomidou.mybatisplus.annotation.EnumValue;
import com.fasterxml.jackson.annotation.JsonValue;
import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 客服工单优先级
 *
 * @author qiujie
 */
@Getter
@AllArgsConstructor
public enum CsTicketPriorityEnum implements BaseEnum<Integer> {

    LOW(1, "低"),
    MEDIUM(2, "中"),
    HIGH(3, "高");

    @JsonValue
    @EnumValue
    private final Integer code;
    private final String message;

    public static CsTicketPriorityEnum of(Integer code) {
        for (CsTicketPriorityEnum value : values()) {
            if (value.code.equals(code)) {
                return value;
            }
        }
        return null;
    }
}
