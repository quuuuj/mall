# 智能客服接入商城：调用链、会话表与前端悬浮窗

## 前言

上一篇《商城接入 LangGraph 多 Agent 客服：服务搭建与问题修复》里，`mall-customer` 作为独立 Python 服务已在本地启动，但还没有接进商城。

本篇记录接入过程：调用链怎么走、会话与消息表怎么设计、Controller 接口，以及门户端的悬浮窗。

## 一、调用链

### 两种接法

用户入口在商城页面，对话能力在 Python 服务，中间隔着 Java 后端，有两种接法：

- 前端直连 `mall-customer` 的 `/api/chat`；
- 浏览器照常请求 `mall-server`，由 Java 转发给 Python 服务。

选了后者，原因有三点：

- **登录态与鉴权在 Java 侧**：`mall-customer` 自身不做鉴权，登录校验、会话归属都依赖 `mall-server` 的 Sa-Token 上下文。前端直连等于把一个无鉴权的大模型接口暴露出去。
- **落库需要一个统一入口**：用户消息、AI 回复要写进 MySQL 的 `cs_message`，首条消息还要生成会话标题，这些都在 Java 侧完成。
- **只暴露一个入口**：开发环境走 Vite 代理，生产走 Nginx，`mall-customer` 只在内网使用。

一次对话经过三个进程：浏览器 → `mall-server`（Java）→ `mall-customer`（Python）。Java 这层还负责鉴权、落库与会话管理：

![客服对话的调用链：浏览器 → mall-server → mall-customer](https://cdn.jsdelivr.net/gh/quuuuj/mall@dev/img/note/02/customer-chat-sequence.png)

`mall-server` 通过 HTTP 调用 `/api/chat`：请求体是 JSON（`user_id`、`session_id`、`message`），应答是 `text/event-stream` 内容分片，浏览器收到一片渲染一片，不用等整段回复。

### HTTP 客户端

三种选择：

- **RestTemplate / RestClient**：Spring 的同步客户端，对流式响应支持弱，RestTemplate 已进入维护模式；
- **JDK HttpClient / OkHttp**：不依赖 Spring，但处理流式响应要自己读 `InputStream`、手工切分 SSE 分片；
- **WebClient**：Spring 的响应式客户端，`bodyToFlux` 直接支持流式响应。

选了 WebClient：

- **依赖已在项目中**：`mall-server` 引入了 `spring-boot-starter-webflux`（Controller 中继流要用 `Flux`），WebClient 随该依赖可用，不必再引第三方 HTTP 库；
- **处理流式更直接**：`bodyToFlux(String.class)` 拿到的就是分片流，不必自己解析 SSE 的 `data:` 前缀与空行分隔；
- **实例可复用**：WebClient 不可变且线程安全，构建一次放在 Spring 容器里即可，也便于统一配置 baseUrl 与超时。

核心调用链：

```java
return customerWebClient.post()
        .uri("/api/chat")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(req)
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(String.class)
        .map(chunk -> { /* 解析分片：取出正文片段，同时拼出完整回复 */ })
        .doOnComplete(() -> { /* 全部收完后，把完整回复落库到 cs_message */ })
        .doOnError(e -> log.error("调用智能客服 SSE 失败: sessionId={}", sessionId, e));
```

客户端配置只固定 Python 服务地址：

```java
@Configuration
public class WebClientConfig {

    /** 智能客服（mall-customer）专用客户端。用于 SSE 长连接中继，不要设置过短的响应超时。 */
    @Bean
    public WebClient customerWebClient(WebClient.Builder builder,
                                       @Value("${mall.customer.url:http://localhost:8000}") String customerApiUrl) {
        return builder.baseUrl(customerApiUrl).build();
    }
}
```

**落库时机**：用户消息在调用 Python 之前落库，模型失败也不会丢失；AI 回复在整段收完后落库，出错只记日志，`cs_message` 里不会出现不完整的回复。

## 二、表设计

会话与消息两张表，都在 MySQL：

```sql
CREATE TABLE `cs_session` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '会话ID',
  `user_id` int NOT NULL COMMENT '用户ID',
  `title` varchar(100) NOT NULL DEFAULT '新对话' COMMENT '会话标题',
  `is_deleted` tinyint NOT NULL DEFAULT 0 COMMENT '逻辑删除: 0未删除 1已删除',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_user_update` (`user_id`, `update_time` DESC)
) ENGINE=InnoDB COMMENT='客服会话表';

CREATE TABLE `cs_message` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '消息ID',
  `session_id` bigint NOT NULL COMMENT '关联会话ID (cs_session.id)',
  `type` varchar(16) NOT NULL COMMENT '发送方类型: user(用户) / assistant(客服)',
  `content` text NOT NULL COMMENT '消息文本内容',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '发送时间',
  PRIMARY KEY (`id`),
  KEY `idx_session_create` (`session_id`, `create_time` ASC)
) ENGINE=InnoDB COMMENT='客服消息明细表';
```

三个设计点：

- **会话标题取首条消息前 20 字**：标题还是默认值"新对话"时，用第一条消息的前 20 个字符替换（超出加省略号）。后端落库时写，前端同步更新本地列表，避免为标题再拉一次接口。
- **会话逻辑删除，消息不级联删**：`cs_session` 用 `@TableLogic` 逻辑删除；消息保留用于排查问题，用户视角里会话已删除。
- **索引按查询建**：`idx_user_update (user_id, update_time DESC)` 支撑会话列表按最近活跃排序，`idx_session_create (session_id, create_time ASC)` 支撑按时间正序拉取消息。

消息从发出到落库：

![消息从发送到落库的完整流程：校验归属 → 落库 → 调用客服 → 流式回复](https://cdn.jsdelivr.net/gh/quuuuj/mall@dev/img/note/02/customer-chat-flow.png)

## 三、Controller 接口

`CustomerController` 有 5 个接口，都要求登录（Sa-Token），挂在 `/portal/customer` 下：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/portal/customer` | 当前用户的会话列表 |
| POST | `/portal/customer` | 新建会话 |
| DELETE | `/portal/customer/{id}` | 删除会话（逻辑删除） |
| GET | `/portal/customer/{sessionId}/messages` | 指定会话的历史消息 |
| POST | `/portal/customer/chat` | 发送消息，SSE 流式返回 |

前四个返回统一的 `ResponseDTO`；`chat` 返回 `Flux<ServerSentEvent<String>>`：

```java
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
```

## 四、前端悬浮窗

入口是跟随页面的全局悬浮按钮：未登录时点击提示"请登录"并跳转登录页，已登录则展开客服面板：

![商城页面右下角的智能客服悬浮入口](https://cdn.jsdelivr.net/gh/quuuuj/mall@dev/img/note/02/portal-customer-entry.png)

面板固定在页面右下角，头部显示"小店助手 / 在线 · 通常 1 分钟内回复"，进入先给一句欢迎语，下面是四个高频问题入口：

![智能客服面板的欢迎态与快捷问题](https://cdn.jsdelivr.net/gh/quuuuj/mall@dev/img/note/02/customer-modal-welcome.png)

会话管理在底部抽屉：新建会话、切换历史会话、删除会话，切换时拉取该会话的历史消息，重开页面也能接着上次聊：

![会话列表抽屉：新建、切换与删除](https://cdn.jsdelivr.net/gh/quuuuj/mall@dev/img/note/02/customer-modal-sessions.png)

## 后续计划

- **工单持久化**：把 `ticket_handler` 的内存存储换成数据库表，重启不丢单；
- **业务数据接入**：让 Python 侧的 Agent 调用 `mall-server` 现成的接口，把订单、物流查询接成工具；
- **多轮上下文**：Redis 短期记忆已经在写入，但还没注入图的状态，多轮追问缺少上下文；
- **Markdown 渲染与换行修复**：让 AI 回复的格式正常显示，并修复聊天过程中换行显示不全的问题。

## 相关链接

- **商城项目主仓库**：<https://github.com/quuuuj/mall>
- **在线体验**：<https://mall.qiujie.net.cn/>（默认体验账号：`admin` / `123456`）
- **上一篇**：《商城接入 LangGraph 多 Agent 客服：服务搭建与问题修复》
