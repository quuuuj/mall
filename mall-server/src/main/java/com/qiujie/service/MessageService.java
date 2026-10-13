package com.qiujie.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.qiujie.entity.Message;
import reactor.core.publisher.Flux;

import java.util.List;

public interface MessageService extends IService<Message> {

    List<Message> listMessagesBySessionId(Long sessionId, Integer userId);

    Flux<String> chat(Long sessionId, String message, Integer userId);
}
