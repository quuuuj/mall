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
     * 该服务只接受带共享密钥的内部调用，密钥以 defaultHeader 形式附加在客户端上，
     * 业务代码无需逐次传递。响应超时不可设得过短，否则大模型出字较慢时会中断流。
     */
    @Bean
    public WebClient customerWebClient(WebClient.Builder builder,
                                       @Value("${mall.customer.url:http://localhost:8000}") String customerApiUrl,
                                       @Value("${mall.customer.token:}") String customerToken) {
        return builder
                .baseUrl(customerApiUrl)
                .defaultHeader("Authorization", "Bearer " + customerToken)
                .build();
    }
}
