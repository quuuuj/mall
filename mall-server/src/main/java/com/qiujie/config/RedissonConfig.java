package com.qiujie.config;

import org.redisson.Redisson;
import org.redisson.api.RedissonClient;
import org.redisson.config.Config;
import org.redisson.config.SingleServerConfig;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.StringUtils;

/**
 * Redisson 客户端配置 — 复用 Spring Redis 连接参数
 * <p>
 * ⚠️ Redisson 使用自有编解码器，不经过 {@code RedisConfig} 的 {@code PrefixStringRedisSerializer}，
 * 通过 RedissonClient 写入的 Key 不会被自动补 {@code spring.data.redis.key-prefix}（{@code mall:}）前缀，
 * 业务代码需自行拼接完整 Key。
 * </p>
 *
 * @author qiujie
 */
@Configuration
public class RedissonConfig {

    @Value("${spring.data.redis.host}")
    private String host;

    @Value("${spring.data.redis.port}")
    private int port;

    @Value("${spring.data.redis.password:}")
    private String password;

    @Value("${spring.data.redis.username:}")
    private String username;

    @Value("${spring.data.redis.database:0}")
    private int database;

    @Bean
    public RedissonClient redissonClient() {
        Config config = new Config();
        SingleServerConfig single = config.useSingleServer()
                .setAddress("redis://" + host + ":" + port)
                .setPassword(password)
                .setDatabase(database);
        if (StringUtils.hasText(username)) {
            single.setUsername(username);
        }
        return Redisson.create(config);
    }
}
