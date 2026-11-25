package com.qiujie.cache;

import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

@Data
@Accessors(chain = true)
public class RedisData {

    private LocalDateTime expireTime;

    private Object data;
}
