package com.qiujie.config;

import com.qiujie.interceptor.InternalTokenInterceptor;
import com.qiujie.interceptor.RateLimitInterceptor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Web MVC 配置
 * <p>
 * 注册自定义拦截器，包括接口限流拦截器 {@link RateLimitInterceptor}
 * 与内部命名空间的共享密钥拦截器 {@link InternalTokenInterceptor}。
 * </p>
 *
 * @author qiujie
 * @date 2026/05/30
 */
@Configuration
public class WebMvcConfig implements WebMvcConfigurer {

    private final RateLimitInterceptor rateLimitInterceptor;
    private final InternalTokenInterceptor internalTokenInterceptor;

    public WebMvcConfig(RateLimitInterceptor rateLimitInterceptor,
                        InternalTokenInterceptor internalTokenInterceptor) {
        this.rateLimitInterceptor = rateLimitInterceptor;
        this.internalTokenInterceptor = internalTokenInterceptor;
    }

    /**
     * 注册拦截器
     *
     * @param registry 拦截器注册表
     */
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(rateLimitInterceptor);
        // /internal/** 不依赖登录态，只接受带共享密钥头调用（Sa-Token 中已排除登录校验）
        registry.addInterceptor(internalTokenInterceptor).addPathPatterns("/internal/**");
    }
}
