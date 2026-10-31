package com.qiujie.interceptor;

import com.qiujie.enums.BusinessStatusEnum;
import com.qiujie.exception.ServiceException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * 内部服务间鉴权拦截器
 * <p>
 * 只作用于 {@code /internal/**}：该命名空间在 Sa-Token 登录拦截中显式排除，
 * 由共享密钥头 {@code X-Internal-Token} 承担鉴权。密钥与调用 mall-customer 时
 * 使用的是同一个（{@code mall.customer.token}），两侧值需一致。
 * <p>
 * 比对使用 {@link MessageDigest#isEqual} 做常量时间比较，避免逐字符比较的时序差异。
 *
 * @author qiujie
 */
@Component
public class InternalTokenInterceptor implements HandlerInterceptor {

    public static final String HEADER = "X-Internal-Token";

    private final String expectedToken;

    public InternalTokenInterceptor(@Value("${mall.customer.token}") String expectedToken) {
        this.expectedToken = expectedToken;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        String provided = request.getHeader(HEADER);
        if (provided == null || provided.isBlank()) {
            throw new ServiceException(BusinessStatusEnum.UNAUTHORIZED);
        }
        if (!constantTimeEquals(provided, expectedToken)) {
            throw new ServiceException(BusinessStatusEnum.FORBIDDEN);
        }
        return true;
    }

    private boolean constantTimeEquals(String a, String b) {
        if (b == null || b.isBlank()) {
            return false;
        }
        return MessageDigest.isEqual(
                a.getBytes(StandardCharsets.UTF_8),
                b.getBytes(StandardCharsets.UTF_8));
    }
}
