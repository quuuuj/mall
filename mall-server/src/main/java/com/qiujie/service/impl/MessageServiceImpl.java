package com.qiujie.service.impl;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.qiujie.entity.Message;
import com.qiujie.entity.Session;
import com.qiujie.exception.ServiceException;
import com.qiujie.mapper.MessageMapper;
import com.qiujie.service.MessageService;
import com.qiujie.service.SessionService;
import com.qiujie.util.CustomerSse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class MessageServiceImpl extends ServiceImpl<MessageMapper, Message> implements MessageService {

    private final SessionService sessionService;
    private final WebClient customerWebClient;

    @Override
    public List<Message> listMessagesBySessionId(Long sessionId, Integer userId) {
        Session session = sessionService.getById(sessionId);
        if (session == null || !session.getUserId().equals(userId)) {
            throw new ServiceException(403, "无权查看该会话或会话不存在");
        }
        return lambdaQuery()
                .eq(Message::getSessionId, sessionId)
                .orderByAsc(Message::getCreateTime)
                .list();
    }

    @Override
    public Flux<String> chat(Long sessionId, String message, Integer userId) {
        Session session = sessionService.getById(sessionId);
        if (session == null || !session.getUserId().equals(userId)) {
            throw new ServiceException(403, "会话不存在或无权访问");
        }

        // 1. 检查是否为新会话的首条消息，若是则更新会话标题
        if ("新对话".equals(session.getTitle())) {
            String title = message.trim();
            if (title.length() > 20) {
                title = title.substring(0, 20) + "...";
            }
            session.setTitle(title);
        }
        session.setUpdateTime(LocalDateTime.now());
        sessionService.updateById(session);

        // 2. 插入用户消息
        Message userMsg = new Message();
        userMsg.setSessionId(sessionId);
        userMsg.setType("user");
        userMsg.setContent(message);
        save(userMsg);

        // 3. 构建请求体调用 Python 智能客服
        Map<String, Object> req = new HashMap<>();
        req.put("message", message);
        req.put("user_id", String.valueOf(userId));
        req.put("session_id", String.valueOf(sessionId));

        StringBuilder fullResponse = new StringBuilder();

        return customerWebClient.post()
                .uri("/api/chat")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(req)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .retrieve()
                .bodyToFlux(String.class)
                .mapNotNull(chunk -> {
                    JSONObject json = parseEvent(chunk);
                    if (json == null) {
                        return null;
                    }
                    String type = json.getString("type");
                    if (CustomerSse.DONE.equals(type)) {
                        // done 由 Java 侧统一补在流尾，避免与上游重复
                        return null;
                    }
                    if (CustomerSse.TOKEN.equals(type)) {
                        String piece = json.getString("content");
                        if (piece != null) {
                            fullResponse.append(piece);
                        }
                    }
                    // ticket / login_required / error 原样中继，由前端按 type 渲染
                    return json.toJSONString();
                })
                .doOnComplete(() -> {
                    // 4. 流传输完成，将完整的回复持久化到 cs_message
                    if (!fullResponse.isEmpty()) {
                        Message assistantMsg = new Message();
                        assistantMsg.setSessionId(sessionId);
                        assistantMsg.setType("assistant");
                        assistantMsg.setContent(fullResponse.toString());
                        save(assistantMsg);
                        log.info("客服会话 [{}] 回复已落库，长度: {}", sessionId, fullResponse.length());
                    }
                })
                .doOnError(e -> {
                    log.error("调用智能客服 SSE 失败: sessionId={}", sessionId, e);
                });
    }

    /**
     * 解析智能客服 SSE 的一条 data 载荷。
     * <p>
     * 协议为单通道 JSON，按 type 分派；解析失败返回 null 并记录告警，
     * 不让单个坏帧中断整条流。
     */
    private JSONObject parseEvent(String chunk) {
        if (chunk == null || chunk.isBlank()) {
            return null;
        }
        try {
            JSONObject json = JSON.parseObject(chunk);
            if (json == null || json.getString("type") == null) {
                log.warn("忽略缺少 type 字段的客服事件: {}", chunk);
                return null;
            }
            return json;
        } catch (Exception e) {
            log.warn("忽略无法解析的客服事件: {}", chunk);
            return null;
        }
    }
}
