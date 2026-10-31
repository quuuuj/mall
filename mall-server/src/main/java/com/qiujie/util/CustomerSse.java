package com.qiujie.util;

import com.alibaba.fastjson2.JSONObject;

/**
 * 智能客服 SSE 协议常量与帧构造。
 * <p>
 * 单通道，每条 {@code data} 为 JSON，按 {@code type} 分派：
 * {@code token} / {@code ticket} / {@code login_required} / {@code error} / {@code done}。
 * Java 侧只做中继与转发，渲染由前端按 type 决定。
 *
 * @author qiujie
 */
public final class CustomerSse {

    /** 增量文本 */
    public static final String TOKEN = "token";
    /** 工单卡片 */
    public static final String TICKET = "ticket";
    /** 需要登录 */
    public static final String LOGIN_REQUIRED = "login_required";
    /** 对用户固定文案的错误 */
    public static final String ERROR = "error";
    /** 流结束标记，必在流尾且只出现一次 */
    public static final String DONE = "done";

    /** 错误事件对用户的固定文案，不透传异常原文 */
    public static final String FALLBACK_ERROR_MESSAGE = "服务暂时不可用，请稍后重试";

    private CustomerSse() {
    }

    public static String doneEvent() {
        return new JSONObject().fluentPut("type", DONE).toJSONString();
    }

    public static String errorEvent() {
        return new JSONObject()
                .fluentPut("type", ERROR)
                .fluentPut("message", FALLBACK_ERROR_MESSAGE)
                .toJSONString();
    }
}
