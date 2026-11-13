package com.qiujie.config;

import io.netty.channel.ChannelOption;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;

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

    /** 建连超时：服务在同一内网，连不上很快就该失败，不必久等 */
    private static final Duration CONNECT_TIMEOUT = Duration.ofSeconds(10);

    /**
     * 两次收到数据之间的最大间隔。
     * <p>
     * 这是 Reactor Netty 的读空闲超时（read timeout），不是整个响应的总时长 ——
     * 大模型首字可能要等十几秒，只要还在持续出字就不会触发；
     * 上游真挂住时才会断开，避免前端一直转圈。
     */
    private static final Duration RESPONSE_TIMEOUT = Duration.ofSeconds(60);

    /**
     * 智能客服（mall-customer）专用客户端。
     * <p>
     * 该服务只接受带共享密钥的内部调用，密钥以 defaultHeader 形式附加在客户端上，
     * 业务代码无需逐次传递。
     */
    @Bean
    public WebClient customerWebClient(WebClient.Builder builder,
                                       @Value("${mall.customer.url:http://localhost:8000}") String customerApiUrl,
                                       @Value("${mall.customer.token}") String customerToken) {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, (int) CONNECT_TIMEOUT.toMillis())
                .responseTimeout(RESPONSE_TIMEOUT);

        return builder
                .baseUrl(customerApiUrl)
                .defaultHeader("Authorization", "Bearer " + customerToken)
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
