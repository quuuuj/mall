package com.qiujie.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

/**
 * WebClient 配置。
 * <p>
 * WebClient 不可变且线程安全，构建一次长期复用即可；每次请求重建会反复装配
 * codecs / exchange strategies，且不利于统一配置超时与连接池。
 *
 * @author qiujie
 */
@Configuration
public class WebClientConfig {

    /**
     * 智能客服（mall-customer）专用客户端。
     * <p>
     * 注意：该客户端用于 SSE 长连接中继，不要设置过短的响应超时，
     * 否则大模型出字较慢时会中断流式输出。
     */
    @Bean
    public WebClient customerWebClient(WebClient.Builder builder,
                                       @Value("${mall.customer.url:http://localhost:8000}") String customerApiUrl) {
        return builder.baseUrl(customerApiUrl).build();
    }
}
