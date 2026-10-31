package com.qiujie.enums;

import com.baomidou.mybatisplus.annotation.EnumValue;
import com.fasterxml.jackson.annotation.JsonValue;
import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 客服工单状态
 * <p>
 * 允许的流转：待处理 → 处理中 / 已关闭；处理中 → 已解决 / 已关闭；
 * 已解决 → 已关闭（用户确认）/ 处理中（用户标记未解决）。
 *
 * @author qiujie
 */
@Getter
@AllArgsConstructor
public enum CsTicketStatusEnum implements BaseEnum<Integer> {

    PENDING(0, "待处理"),
    PROCESSING(1, "处理中"),
    RESOLVED(2, "已解决"),
    CLOSED(3, "已关闭");

    @JsonValue
    @EnumValue
    private final Integer code;
    private final String message;

    public static CsTicketStatusEnum of(Integer code) {
        for (CsTicketStatusEnum value : values()) {
            if (value.code.equals(code)) {
                return value;
            }
        }
        return null;
    }
}
