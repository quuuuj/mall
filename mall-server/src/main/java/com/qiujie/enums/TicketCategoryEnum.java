package com.qiujie.enums;

import com.baomidou.mybatisplus.annotation.EnumValue;
import com.fasterxml.jackson.annotation.JsonValue;
import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 客服工单类型
 *
 * @author qiujie
 */
@Getter
@AllArgsConstructor
public enum TicketCategoryEnum implements DictEnum<Integer> {

    REFUND_RETURN(1, "退款退货"),
    LOGISTICS(2, "物流异常"),
    INVOICE(3, "发票"),
    COMPLAINT(4, "投诉建议");

    @JsonValue
    @EnumValue
    private final Integer code;
    private final String text;

    public static TicketCategoryEnum of(Integer code) {
        for (TicketCategoryEnum value : values()) {
            if (value.code.equals(code)) {
                return value;
            }
        }
        return null;
    }
}
