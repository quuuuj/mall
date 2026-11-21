package com.qiujie.enums;

import lombok.Getter;

/**
 * 统一响应码。
 * <p>
 * 五位编码：前三位对齐 HTTP 状态码语义，后两位为类目内子码，按步长 10 预留间隔。
 * 例：40100 对应 HTTP 401（未认证），40110 为同类目下的登录失败。
 */
@Getter
public enum BusinessStatusEnum implements BaseEnum<Integer> {

    SUCCESS(20000, "成功"),
    PARAM_ERROR(40000, "参数错误"),
    ADDRESS_NOT_EXIST(40010, "请先添加收货地址"),
    UNAUTHORIZED(40100, "认证失败，请重新登录"),
    LOGIN_FAILED(40110, "用户名或密码错误"),
    FORBIDDEN(40300, "你没有此权限"),
    NOT_FOUND(40400, "资源不存在"),
    CONFLICT(40900, "操作冲突，请刷新后重试"),
    RATE_LIMITED(42900, "请求过于频繁，请稍后再试"),
    SERVER_ERROR(50000, "服务器内部错误");

    private final Integer code;
    private final String message;

    BusinessStatusEnum(Integer code, String message) {
        this.code = code;
        this.message = message;
    }
}
