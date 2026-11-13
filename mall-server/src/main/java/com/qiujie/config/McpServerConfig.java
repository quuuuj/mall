package com.qiujie.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.qiujie.dto.TicketCreateRequest;
import com.qiujie.dto.TicketCreateResponse;
import com.qiujie.entity.Order;
import com.qiujie.entity.OrderItem;
import com.qiujie.service.OrderService;
import com.qiujie.service.TicketService;
import io.modelcontextprotocol.json.McpJsonMapper;
import io.modelcontextprotocol.json.jackson.JacksonMcpJsonMapper;
import io.modelcontextprotocol.server.McpServer;
import io.modelcontextprotocol.server.McpStatelessServerFeatures;
import io.modelcontextprotocol.server.McpStatelessSyncServer;
import io.modelcontextprotocol.server.transport.WebMvcStatelessServerTransport;
import io.modelcontextprotocol.spec.McpSchema;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * MCP 工具服务 — 把后端业务操作以 MCP 工具的形式暴露给 mall-customer。
 * <p>
 * 端点 {@code /mcp}，采用 Streamable HTTP 的无状态传输：每个请求自带完整 JSON-RPC 消息，
 * 服务端不保存会话。鉴权沿用共享密钥头 {@code X-Internal-Token}，
 * 由 {@code McpTokenInterceptor} 在路由函数命中前校验。
 * <p>
 * 暴露的工具：
 * <ul>
 *   <li>{@code create_ticket} — 建单（写）</li>
 *   <li>{@code get_order_by_sn} — 按订单号查自己的订单（只读）</li>
 *   <li>{@code list_recent_orders} — 查自己最近的订单（只读）</li>
 * </ul>
 * 订单类工具一律以 {@code userId} 为归属条件，Agent 传错的号只会查不到，查不到别人的单。
 * <p>
 * 业务校验与写入仍由 {@link TicketService} / {@link OrderService} 完成，
 * 这里只做协议层的参数解析与结果封装。
 *
 * @author qiujie
 */
@Configuration
public class McpServerConfig {

    public static final String ENDPOINT = "/mcp";

    /** 订单类工具返回给 Agent 的时间格式 */
    private static final DateTimeFormatter TIME_FORMAT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    /** 查最近订单的默认条数 */
    private static final int DEFAULT_RECENT_LIMIT = 5;

    @Bean
    public McpJsonMapper mcpJsonMapper(ObjectMapper objectMapper) {
        return new JacksonMcpJsonMapper(objectMapper);
    }

    @Bean
    public WebMvcStatelessServerTransport mcpTransport() {
        return WebMvcStatelessServerTransport.builder()
                .messageEndpoint(ENDPOINT)
                .build();
    }

    @Bean(destroyMethod = "close")
    public McpStatelessSyncServer mcpServer(WebMvcStatelessServerTransport transport,
                                            TicketService ticketService,
                                            OrderService orderService,
                                            McpJsonMapper jsonMapper) {
        return McpServer.sync(transport)
                .serverInfo("mall-server", "1.0.0")
                .instructions("mall 商城后端业务工具，仅供智能客服内部调用")
                .jsonMapper(jsonMapper)
                .tools(
                        createTicketTool(ticketService, jsonMapper),
                        getOrderBySnTool(orderService, jsonMapper),
                        listRecentOrdersTool(orderService, jsonMapper)
                )
                .build();
    }

    /**
     * 把 MCP 传输层自带的路由函数交给 Spring MVC。
     * <p>
     * 该 RouterFunction 内部已绑定 MCP handler，由 RouterFunctionMapping 负责匹配；
     * 拦截器对映射到路由函数的请求同样生效，所以共享密钥校验无需在工具内重复。
     */
    @Bean
    public RouterFunction<ServerResponse> mcpRouterFunction(WebMvcStatelessServerTransport transport) {
        return transport.getRouterFunction();
    }

    private McpStatelessServerFeatures.SyncToolSpecification createTicketTool(
            TicketService ticketService, McpJsonMapper jsonMapper) {
        return McpStatelessServerFeatures.SyncToolSpecification.builder()
                .tool(McpSchema.Tool.builder()
                        .name("create_ticket")
                        .description("创建客服工单并返回工单号")
                        .inputSchema(jsonMapper, """
                                {
                                  "type": "object",
                                  "properties": {
                                    "userId": {"type": "integer", "description": "诉求所属用户 ID"},
                                    "sessionId": {"type": "integer", "description": "触发建单的客服会话 ID"},
                                    "category": {"type": "integer", "description": "1 退款退货 / 2 物流异常 / 3 发票 / 4 投诉建议"},
                                    "priority": {"type": "integer", "description": "1 低 / 2 中 / 3 高；不传按类型取默认值"},
                                    "summary": {"type": "string", "description": "一句话摘要，不超过 200 字"},
                                    "detail": {"type": "string", "description": "结构化字段 JSON，四类工单各自的必填字段"},
                                    "needsInfo": {"type": "integer", "description": "是否仍缺字段: 1 是 / 0 否"}
                                  },
                                  "required": ["userId", "sessionId", "category", "summary"]
                                }
                                """)
                        .build())
                .callHandler((context, request) -> {
                    try {
                        return McpSchema.CallToolResult.builder()
                                .addTextContent(jsonText(jsonMapper, toTicketView(
                                        ticketService.create(toRequest(request.arguments())))))
                                .build();
                    } catch (RuntimeException e) {
                        // 参数或业务校验失败：如实回给调用方，由 Agent 转述给用户
                        return McpSchema.CallToolResult.builder()
                                .addTextContent("建单失败: " + e.getMessage())
                                .isError(true)
                                .build();
                    }
                })
                .build();
    }

    /**
     * 按订单号查订单（只读）。归属校验在 Service 层按 userId 过滤，
     * 订单不属于该用户时与不存在同样返回 isError，不泄露他人订单是否存在。
     */
    private McpStatelessServerFeatures.SyncToolSpecification getOrderBySnTool(OrderService orderService,
                                                                            McpJsonMapper jsonMapper) {
        return McpStatelessServerFeatures.SyncToolSpecification.builder()
                .tool(McpSchema.Tool.builder()
                        .name("get_order_by_sn")
                        .description("按订单号查询当前用户自己的订单详情（只读，不含他人订单）")
                        .inputSchema(jsonMapper, """
                                {
                                  "type": "object",
                                  "properties": {
                                    "userId": {"type": "integer", "description": "发起查询的用户 ID，订单归属由此字段约束"},
                                    "orderSn": {"type": "string", "description": "订单号"}
                                  },
                                  "required": ["userId", "orderSn"]
                                }
                                """)
                        .build())
                .callHandler((context, request) -> {
                    try {
                        Order order = orderService.detailByOrderSn(
                                asInteger(request.arguments().get("userId")),
                                asString(request.arguments().get("orderSn")));
                        return McpSchema.CallToolResult.builder()
                                .addTextContent(jsonText(jsonMapper, toOrderView(order)))
                                .build();
                    } catch (RuntimeException e) {
                        return errorResult(e);
                    }
                })
                .build();
    }

    /**
     * 查当前用户最近的订单（只读），按创建时间倒序，最多 10 条。
     */
    private McpStatelessServerFeatures.SyncToolSpecification listRecentOrdersTool(OrderService orderService,
                                                                                 McpJsonMapper jsonMapper) {
        return McpStatelessServerFeatures.SyncToolSpecification.builder()
                .tool(McpSchema.Tool.builder()
                        .name("list_recent_orders")
                        .description("查询当前用户最近的订单列表（只读，按创建时间倒序）")
                        .inputSchema(jsonMapper, """
                                {
                                  "type": "object",
                                  "properties": {
                                    "userId": {"type": "integer", "description": "发起查询的用户 ID"},
                                    "limit": {"type": "integer", "description": "返回条数，默认 5，最多 10"}
                                  },
                                  "required": ["userId"]
                                }
                                """)
                        .build())
                .callHandler((context, request) -> {
                    try {
                        Integer limit = asInteger(request.arguments().get("limit"));
                        List<Order> orders = orderService.listRecent(
                                asInteger(request.arguments().get("userId")),
                                limit == null ? DEFAULT_RECENT_LIMIT : limit);
                        List<Map<String, Object>> views = orders.stream().map(this::toOrderView).toList();
                        return McpSchema.CallToolResult.builder()
                                .addTextContent(jsonText(jsonMapper,
                                        Map.of("orders", views, "total", views.size())))
                                .build();
                    } catch (RuntimeException e) {
                        return errorResult(e);
                    }
                })
                .build();
    }

    /**
     * 订单转成 Agent 易读的精简结构：只给用户能理解的字段，
     * 不含 userId / 地址 ID / 支付流水号等内部标识。
     * <p>
     * 注意库里没有运单号字段，只能给「已发货 + 发货时间」，无法回答到哪了。
     */
    private Map<String, Object> toOrderView(Order order) {
        List<Map<String, Object>> items = order.getItems() == null ? List.of() : order.getItems().stream()
                .map(this::toItemView)
                .toList();
        return new LinkedHashMap<>() {{
            put("orderSn", order.getOrderSn());
            put("status", order.getStatus() == null ? null : order.getStatus().getMessage());
            put("totalAmount", order.getTotalAmount());
            put("createTime", formatTime(order.getCreateTime()));
            put("paymentTime", formatTime(order.getPaymentTime()));
            put("deliveryTime", formatTime(order.getDeliveryTime()));
            put("receiptTime", formatTime(order.getReceiptTime()));
            put("items", items);
        }};
    }

    private Map<String, Object> toItemView(OrderItem item) {
        return new LinkedHashMap<>() {{
            put("productName", item.getProductName());
            put("price", item.getProductPrice());
            put("amount", item.getAmount());
        }};
    }

    private String formatTime(java.time.LocalDateTime time) {
        return time == null ? null : time.format(TIME_FORMAT);
    }

    private McpSchema.CallToolResult errorResult(RuntimeException e) {
        return McpSchema.CallToolResult.builder()
                .addTextContent("查询失败: " + e.getMessage())
                .isError(true)
                .build();
    }

    /**
     * 工具结果统一用 JSON 文本返回，调用方直接解析字段。
     * <p>
     * 走 MCP 协议层的 JsonMapper（Jackson），不手写字符串拼接 ——
     * 摘要里可能出现引号、换行，拼接出来的 JSON 会直接损坏。
     */
    private String jsonText(McpJsonMapper jsonMapper, Object value) {
        try {
            return jsonMapper.writeValueAsString(value);
        } catch (Exception e) {
            throw new IllegalStateException("工具结果序列化失败", e);
        }
    }

    private Map<String, Object> toTicketView(TicketCreateResponse response) {
        return new LinkedHashMap<>() {{
            put("ticketNo", response.getTicketNo());
            put("category", response.getCategory());
            put("status", response.getStatus());
            put("createTime", response.getCreateTime() == null ? null : response.getCreateTime().toString());
        }};
    }

    private TicketCreateRequest toRequest(Map<String, Object> arguments) {
        TicketCreateRequest request = new TicketCreateRequest();
        request.setUserId(asInteger(arguments.get("userId")));
        request.setSessionId(asLong(arguments.get("sessionId")));
        request.setCategory(asInteger(arguments.get("category")));
        request.setPriority(asInteger(arguments.get("priority")));
        request.setSummary(asString(arguments.get("summary")));
        request.setDetail(asString(arguments.get("detail")));
        Integer needsInfo = asInteger(arguments.get("needsInfo"));
        request.setNeedsInfo(needsInfo == null ? 0 : needsInfo);
        return request;
    }

    private Integer asInteger(Object value) {
        return value == null ? null : Integer.valueOf(String.valueOf(value));
    }

    private Long asLong(Object value) {
        return value == null ? null : Long.valueOf(String.valueOf(value));
    }

    private String asString(Object value) {
        return value == null ? null : String.valueOf(value);
    }
}
