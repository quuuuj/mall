package com.qiujie.interceptor;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * MCP 端点鉴权拦截器
 * <p>
 * 只作用于 {@code /mcp}：该路径在 Sa-Token 登录拦截中显式排除，由共享密钥头
 * {@code X-Internal-Token} 承担鉴权。密钥与调用 mall-customer 时用的是同一个
 * （{@code mall.customer.token}），两侧值需一致。
 * <p>
 * 调用方是另一端服务而不是浏览器，鉴权失败直接回真实 HTTP 状态码（401/403），
 * 不走全局「HTTP 200 + body 业务码」的约定，MCP 客户端才能按协议分支处理。
 * <p>
 * 比对使用 {@link MessageDigest#isEqual} 做常量时间比较，避免逐字符比较的时序差异。
 *
 * @author qiujie
 */
@Component
public class McpTokenInterceptor implements HandlerInterceptor {

    public static final String HEADER = "X-Internal-Token";

    private static final Logger logger = LoggerFactory.getLogger(McpTokenInterceptor.class);

    private final String expectedToken;

    public McpTokenInterceptor(@Value("${mall.customer.token}") String expectedToken) {
        this.expectedToken = expectedToken;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler)
            throws IOException {
        String provided = request.getHeader(HEADER);
        if (provided == null || provided.isBlank()) {
            return reject(response, HttpServletResponse.SC_UNAUTHORIZED);
        }
        if (!constantTimeEquals(provided, expectedToken)) {
            return reject(response, HttpServletResponse.SC_FORBIDDEN);
        }
        return true;
    }

    private boolean reject(HttpServletResponse response, int status) throws IOException {
        logger.info("MCP 请求鉴权失败: status={}", status);
        response.setStatus(status);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"error\":\"unauthorized\"}");
        return false;
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
