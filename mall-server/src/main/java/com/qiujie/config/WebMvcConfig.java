package com.qiujie.config;

import com.qiujie.interceptor.McpTokenInterceptor;
import com.qiujie.interceptor.RateLimitInterceptor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Web MVC 配置
 * <p>
 * 注册自定义拦截器，包括接口限流拦截器 {@link RateLimitInterceptor}
 * 与 MCP 工具端点的共享密钥拦截器 {@link McpTokenInterceptor}。
 * </p>
 *
 * @author qiujie
 * @date 2026/05/30
 */
@Configuration
public class WebMvcConfig implements WebMvcConfigurer {

    private final RateLimitInterceptor rateLimitInterceptor;
    private final McpTokenInterceptor mcpTokenInterceptor;

    public WebMvcConfig(RateLimitInterceptor rateLimitInterceptor,
                        McpTokenInterceptor mcpTokenInterceptor) {
        this.rateLimitInterceptor = rateLimitInterceptor;
        this.mcpTokenInterceptor = mcpTokenInterceptor;
    }

    /**
     * 注册拦截器
     *
     * @param registry 拦截器注册表
     */
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(rateLimitInterceptor);
        // /mcp 不依赖登录态，只接受带共享密钥头调用（Sa-Token 中已排除登录校验）
        registry.addInterceptor(mcpTokenInterceptor).addPathPatterns(McpServerConfig.ENDPOINT);
    }
}
