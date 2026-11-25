package com.qiujie.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.experimental.Accessors;

import java.time.LocalDateTime;

@Data
@Accessors(chain = true)
@TableName("cs_message")
public class Message {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("session_id")
    private Long sessionId;

    /**
     * 发送方类型: user(用户) / assistant(客服) / system(系统通知)
     * <p>
     * system 用于工单状态变更等平台侧提示，由服务端写入，前端居中灰底渲染、不带头像。
     */
    @TableField("type")
    private String type;

    @TableField("content")
    private String content;

    @TableField("create_time")
    private LocalDateTime createTime;
}
