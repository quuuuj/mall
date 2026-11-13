package com.qiujie.enums;

import com.baomidou.mybatisplus.annotation.EnumValue;
import com.fasterxml.jackson.annotation.JsonValue;
import lombok.AllArgsConstructor;
import lombok.Getter;

import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

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
public enum TicketStatusEnum implements BaseEnum<Integer> {

    PENDING(0, "待处理"),
    PROCESSING(1, "处理中"),
    RESOLVED(2, "已解决"),
    CLOSED(3, "已关闭");

    /**
     * 状态机：key 为当前状态，value 为允许流转到的目标状态。
     * 已关闭是终态；不允许回退到待处理（用户重新打开走已解决 → 处理中）。
     */
    private static final Map<TicketStatusEnum, Set<TicketStatusEnum>> TRANSITIONS = Map.of(
            PENDING, EnumSet.of(PROCESSING, CLOSED),
            PROCESSING, EnumSet.of(RESOLVED, CLOSED),
            RESOLVED, EnumSet.of(CLOSED, PROCESSING),
            CLOSED, EnumSet.noneOf(TicketStatusEnum.class)
    );

    @JsonValue
    @EnumValue
    private final Integer code;
    private final String message;

    public static TicketStatusEnum of(Integer code) {
        for (TicketStatusEnum value : values()) {
            if (value.code.equals(code)) {
                return value;
            }
        }
        return null;
    }

    /**
     * 是否允许从本状态流转到目标状态。
     */
    public boolean canTransitionTo(TicketStatusEnum target) {
        return TRANSITIONS.getOrDefault(this, Set.of()).contains(target);
    }
}
