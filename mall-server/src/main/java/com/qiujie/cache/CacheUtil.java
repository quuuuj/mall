package com.qiujie.cache;

import cn.hutool.core.util.BooleanUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;
import java.util.function.Supplier;

import static com.qiujie.common.RedisConstants.*;

/**
 * 缓存工具 — 逻辑过期防击穿
 *
 * @author qiujie
 */
@Component
public class CacheUtil {

    private static final ExecutorService CACHE_REBUILD_EXECUTOR = Executors.newFixedThreadPool(10);

    private final StringRedisTemplate stringRedisTemplate;

    public CacheUtil(StringRedisTemplate stringRedisTemplate) {
        this.stringRedisTemplate = stringRedisTemplate;
    }

    /**
     * 逻辑过期：按「keyPrefix + id」拼 Key
     */
    public <T, ID> T queryWithLogicalExpire(String keyPrefix, ID id, Class<T> clazz,
                                            Function<ID, T> dbFallback, Long timeout, TimeUnit timeUnit) {
        String key = keyPrefix + id;
        String jsonStr = stringRedisTemplate.opsForValue().get(key);
        if (StrUtil.isBlank(jsonStr)) {
            T t = dbFallback.apply(id);
            if (t != null) {
                this.setWithLogicalExpire(key, t, timeout, timeUnit);
            }
            return t;
        }
        RedisData redisData = JSONUtil.toBean(jsonStr, RedisData.class);
        T t = toBean(redisData.getData(), clazz);
        if (redisData.getExpireTime().isAfter(LocalDateTime.now())) {
            return t;
        }
        String lockKey = LOCK_PRODUCT_KEY + id;
        if (tryLock(lockKey)) {
            CACHE_REBUILD_EXECUTOR.submit(() -> {
                try {
                    T t1 = dbFallback.apply(id);
                    if (t1 != null) {
                        this.setWithLogicalExpire(key, t1, timeout, timeUnit);
                    }
                } finally {
                    unLock(lockKey);
                }
            });
        }
        return t;
    }

    /**
     * 逻辑过期：直接传完整 Key
     */
    public <T> T queryWithLogicalExpire(String fullKey, Class<T> clazz,
                                         Supplier<T> dbFallback, Long timeout, TimeUnit timeUnit) {
        String jsonStr = stringRedisTemplate.opsForValue().get(fullKey);
        if (StrUtil.isBlank(jsonStr)) {
            T t = dbFallback.get();
            if (t != null) {
                this.setWithLogicalExpire(fullKey, t, timeout, timeUnit);
            }
            return t;
        }
        RedisData redisData = JSONUtil.toBean(jsonStr, RedisData.class);
        T t = toBean(redisData.getData(), clazz);
        if (redisData.getExpireTime().isAfter(LocalDateTime.now())) {
            return t;
        }
        String lockKey = LOCK_PRODUCT_KEY + fullKey;
        if (tryLock(lockKey)) {
            CACHE_REBUILD_EXECUTOR.submit(() -> {
                try {
                    T t1 = dbFallback.get();
                    if (t1 != null) {
                        this.setWithLogicalExpire(fullKey, t1, timeout, timeUnit);
                    }
                } finally {
                    unLock(lockKey);
                }
            });
        }
        return t;
    }

    public void delete(String key) {
        stringRedisTemplate.delete(key);
    }

    private void setWithLogicalExpire(String key, Object value, Long timeout, TimeUnit timeUnit) {
        RedisData redisData = new RedisData().setData(value);
        redisData.setExpireTime(LocalDateTime.now().plusSeconds(timeUnit.toSeconds(timeout)));
        stringRedisTemplate.opsForValue().set(key, JSONUtil.toJsonStr(redisData));
    }

    @SuppressWarnings("unchecked")
    private static <T> T toBean(Object data, Class<T> clazz) {
        if (data == null) return null;
        // JSONArray 继承 ArrayList，可直接作为 List 返回
        if (data instanceof cn.hutool.json.JSONArray) {
            return (T) data;
        }
        if (data instanceof JSONObject jo) {
            return JSONUtil.toBean(jo, clazz);
        }
        return (T) JSONUtil.toBean(JSONUtil.toJsonStr(data), clazz);
    }

    private boolean tryLock(String key) {
        Boolean flag = stringRedisTemplate.opsForValue().setIfAbsent(key, "1", LOCK_TTL, TimeUnit.SECONDS);
        return BooleanUtil.isTrue(flag);
    }

    private void unLock(String key) {
        stringRedisTemplate.delete(key);
    }
}
