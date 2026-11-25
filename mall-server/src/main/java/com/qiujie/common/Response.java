package com.qiujie.common;

import com.qiujie.enums.BusinessStatusEnum;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 统一响应体
 */
@Getter
@AllArgsConstructor(access = AccessLevel.PRIVATE)
@Schema(description = "统一响应体")
public class Response<T> {

    @Schema(description = "状态码")
    private Integer code;

    @Schema(description = "响应消息")
    private String message;

    @Schema(description = "响应数据")
    private T data;

    public static <T> Response<T> success() {
        return new Response<>(BusinessStatusEnum.SUCCESS.getCode(), "成功", null);
    }

    public static <T> Response<T> success(T data) {
        return new Response<>(BusinessStatusEnum.SUCCESS.getCode(), "成功", data);
    }

    public static Response<Void> ok(String message) {
        return new Response<>(BusinessStatusEnum.SUCCESS.getCode(), message, null);
    }

    public static <T> Response<T> error(Integer code, String message) {
        return new Response<>(code, message, null);
    }

    public static <T> Response<T> error(BusinessStatusEnum e) {
        return new Response<>(e.getCode(), e.getMessage(), null);
    }
}
