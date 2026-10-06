package com.qiujie.controller.portal;

import cn.dev33.satoken.stp.StpUtil;
import com.qiujie.dto.Response;
import com.qiujie.dto.ResponseDTO;
import com.qiujie.entity.Message;
import com.qiujie.entity.Session;
import com.qiujie.service.MessageService;
import com.qiujie.service.SessionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/portal/customer")
@RequiredArgsConstructor
@Tag(name = "门户端-智能客服")
public class CustomerController {

    private final SessionService sessionService;
    private final MessageService messageService;

    @Operation(summary = "获取当前用户的客服会话列表")
    @GetMapping
    public ResponseDTO<List<Session>> listSessions() {
        Integer userId = StpUtil.getLoginIdAsInt();
        return Response.success(sessionService.listUserSessions(userId));
    }

    @Operation(summary = "创建新会话")
    @PostMapping
    public ResponseDTO<Session> createSession() {
        Integer userId = StpUtil.getLoginIdAsInt();
        return Response.success(sessionService.create(userId));
    }

    @Operation(summary = "删除会话")
    @DeleteMapping("/{id}")
    public ResponseDTO<Void> deleteSession(@PathVariable("id") Long id) {
        Integer userId = StpUtil.getLoginIdAsInt();
        sessionService.delete(id, userId);
        return Response.ok("删除会话成功");
    }

    @Operation(summary = "获取指定会话的历史消息")
    @GetMapping("/{sessionId}/messages")
    public ResponseDTO<List<Message>> listMessages(@PathVariable("sessionId") Long sessionId) {
        Integer userId = StpUtil.getLoginIdAsInt();
        return Response.success(messageService.listMessagesBySessionId(sessionId, userId));
    }

    @Operation(summary = "发送消息并流式返回回复")
    @PostMapping(value = "/chat", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> chat(@RequestBody Map<String, Object> body) {
        Integer userId = StpUtil.getLoginIdAsInt();
        Long sessionId = Long.valueOf(body.get("sessionId").toString());
        String message = body.get("message").toString();

        return messageService.chat(sessionId, message, userId)
                .map(content -> ServerSentEvent.<String>builder()
                        .data(content)
                        .build())
                .concatWith(Flux.just(ServerSentEvent.<String>builder()
                        .event("done")
                        .data("[DONE]")
                        .build()));
    }
}
