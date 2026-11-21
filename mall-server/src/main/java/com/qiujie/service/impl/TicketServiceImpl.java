package com.qiujie.service.impl;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.qiujie.dto.TicketCreateRequest;
import com.qiujie.enums.BusinessStatusEnum;
import com.qiujie.vo.TicketCreateVO;
import com.qiujie.vo.TicketDetailVO;
import com.qiujie.vo.TicketListItemVO;
import com.qiujie.dto.TicketStatusUpdateRequest;
import com.qiujie.entity.Ticket;
import com.qiujie.entity.TicketLog;
import com.qiujie.entity.Message;
import com.qiujie.entity.User;
import com.qiujie.enums.TicketCategoryEnum;
import com.qiujie.enums.TicketPriorityEnum;
import com.qiujie.enums.TicketStatusEnum;
import com.qiujie.exception.BusinessException;
import com.qiujie.mapper.TicketLogMapper;
import com.qiujie.mapper.TicketMapper;
import com.qiujie.mapper.MessageMapper;
import com.qiujie.mapper.UserMapper;
import com.qiujie.service.TicketService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;
import java.util.stream.Collectors;

/**
 * 客服工单服务实现
 * <p>
 * 建单与日志在同一事务内写入；工单号与自增主键分离，对外只暴露工单号。
 *
 * @author qiujie
 */
@Slf4j
@Service
public class TicketServiceImpl extends ServiceImpl<TicketMapper, Ticket> implements TicketService {

    private static final DateTimeFormatter DAY = DateTimeFormatter.ofPattern("yyyyMMdd");
    private static final int TICKET_NO_RETRY = 5;
    private static final int SYSTEM_OPERATOR = 0;

    /** cs_message.type 取值：平台侧系统通知（工单状态变更等） */
    private static final String MESSAGE_TYPE_SYSTEM = "system";

    /**
     * 四类工单的必填字段（detail JSON 的 key）。needsInfo=1 时不做校验：
     * 两轮追问后仍缺字段也要能建单，否则用户诉求无出口。
     */
    private static final Map<TicketCategoryEnum, List<String>> REQUIRED_FIELDS = Map.of(
            TicketCategoryEnum.REFUND_RETURN, List.of("orderNo", "reason", "received"),
            TicketCategoryEnum.LOGISTICS, List.of("orderNo", "phenomenon"),
            TicketCategoryEnum.INVOICE, List.of("orderNo", "title", "taxNo"),
            TicketCategoryEnum.COMPLAINT, List.of("description")
    );

    /**
     * 各类工单的默认优先级
     */
    private static final Map<TicketCategoryEnum, TicketPriorityEnum> DEFAULT_PRIORITY = Map.of(
            TicketCategoryEnum.REFUND_RETURN, TicketPriorityEnum.MEDIUM,
            TicketCategoryEnum.LOGISTICS, TicketPriorityEnum.MEDIUM,
            TicketCategoryEnum.INVOICE, TicketPriorityEnum.LOW,
            TicketCategoryEnum.COMPLAINT, TicketPriorityEnum.HIGH
    );

    private final TicketLogMapper ticketLogMapper;
    private final MessageMapper messageMapper;
    private final UserMapper userMapper;

    public TicketServiceImpl(TicketLogMapper ticketLogMapper, MessageMapper messageMapper,
                               UserMapper userMapper) {
        this.ticketLogMapper = ticketLogMapper;
        this.messageMapper = messageMapper;
        this.userMapper = userMapper;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public TicketCreateVO create(TicketCreateRequest request) {
        TicketCategoryEnum category = TicketCategoryEnum.of(request.getCategory());
        if (category == null) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "工单类型不合法");
        }

        TicketPriorityEnum priority = resolvePriority(request, category);
        boolean needsInfo = Integer.valueOf(1).equals(request.getNeedsInfo());

        JSONObject detail = parseDetail(request.getDetail());
        if (!needsInfo) {
            assertRequiredFields(category, detail);
        }

        LocalDateTime now = LocalDateTime.now();
        Ticket ticket = new Ticket()
                .setTicketNo(nextTicketNo(now))
                .setUserId(request.getUserId())
                .setSessionId(request.getSessionId())
                .setCategory(category)
                .setStatus(TicketStatusEnum.PENDING)
                .setPriority(priority)
                .setSummary(request.getSummary())
                .setDetail(detail == null ? null : detail.toJSONString())
                .setAdminRemark("")
                .setNeedsInfo(needsInfo ? 1 : 0)
                .setCreateTime(now)
                .setUpdateTime(now);
        save(ticket);

        // 建单日志：from_status 为空，操作人记为系统
        ticketLogMapper.insert(new TicketLog()
                .setTicketId(ticket.getId())
                .setOperatorId(SYSTEM_OPERATOR)
                .setFromStatus(null)
                .setToStatus(TicketStatusEnum.PENDING)
                .setRemark("建单")
                .setCreateTime(now));

        log.info("客服工单已创建: ticketNo={}, userId={}, sessionId={}, category={}, needsInfo={}",
                ticket.getTicketNo(), ticket.getUserId(), ticket.getSessionId(), category, needsInfo);

        return new TicketCreateVO(
                ticket.getTicketNo(),
                category.getText(),
                TicketStatusEnum.PENDING.getText(),
                now);
    }

    private TicketPriorityEnum resolvePriority(TicketCreateRequest request, TicketCategoryEnum category) {
        if (request.getPriority() == null) {
            return DEFAULT_PRIORITY.get(category);
        }
        TicketPriorityEnum priority = TicketPriorityEnum.of(request.getPriority());
        if (priority == null) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "工单优先级不合法");
        }
        return priority;
    }

    private JSONObject parseDetail(String detail) {
        if (detail == null || detail.isBlank()) {
            return null;
        }
        try {
            return JSON.parseObject(detail);
        } catch (Exception e) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "工单结构化字段不是合法 JSON");
        }
    }

    private void assertRequiredFields(TicketCategoryEnum category, JSONObject detail) {
        List<String> required = REQUIRED_FIELDS.getOrDefault(category, List.of());
        if (required.isEmpty()) {
            return;
        }
        java.util.Set<String> present = detail == null ? java.util.Set.of() : detail.keySet();
        List<String> missing = required.stream().filter(key -> !present.contains(key)).toList();
        if (!missing.isEmpty()) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "缺少必填字段: " + String.join(", ", missing));
        }
    }

    // ─── 管理端查询 ───

    @Override
    public IPage<TicketListItemVO> list(Integer current, Integer size, Integer status, Integer category,
                                        String startTime, String endTime) {
        TicketStatusEnum statusFilter = null;
        if (status != null) {
            statusFilter = TicketStatusEnum.of(status);
            if (statusFilter == null) {
                throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "状态筛选值不合法");
            }
        }
        TicketCategoryEnum categoryFilter = null;
        if (category != null) {
            categoryFilter = TicketCategoryEnum.of(category);
            if (categoryFilter == null) {
                throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "类型筛选值不合法");
            }
        }

        LambdaQueryWrapper<Ticket> query = Wrappers.<Ticket>lambdaQuery()
                .eq(statusFilter != null, Ticket::getStatus, statusFilter)
                .eq(categoryFilter != null, Ticket::getCategory, categoryFilter)
                .ge(hasText(startTime), Ticket::getCreateTime, parseLowerBound(startTime))
                .le(hasText(endTime), Ticket::getCreateTime, parseUpperBound(endTime))
                .orderByDesc(Ticket::getCreateTime);

        IPage<Ticket> page = page(new Page<>(Math.max(current, 1), Math.max(size, 1)), query);
        Map<Integer, String> userNames = userNamesOf(
                page.getRecords().stream().map(Ticket::getUserId).distinct().toList());

        return page.convert(ticket -> {
            TicketListItemVO item = new TicketListItemVO();
            item.setTicketNo(ticket.getTicketNo());
            item.setUserId(ticket.getUserId());
            item.setUserName(userNames.get(ticket.getUserId()));
            item.setSummary(ticket.getSummary());
            item.setNeedsInfo(Integer.valueOf(1).equals(ticket.getNeedsInfo()));
            item.setCreateTime(ticket.getCreateTime());
            if (ticket.getCategory() != null) {
                item.setCategory(ticket.getCategory().getCode());
                item.setCategoryText(ticket.getCategory().getText());
            }
            if (ticket.getStatus() != null) {
                item.setStatus(ticket.getStatus().getCode());
                item.setStatusText(ticket.getStatus().getText());
            }
            if (ticket.getPriority() != null) {
                item.setPriority(ticket.getPriority().getCode());
                item.setPriorityText(ticket.getPriority().getText());
            }
            return item;
        });
    }

    @Override
    public TicketDetailVO detail(String ticketNo) {
        Ticket ticket = getByTicketNo(ticketNo);

        TicketDetailVO detail = new TicketDetailVO();
        detail.setTicket(toView(ticket));
        List<Message> messages = messageMapper.selectList(Wrappers.<Message>lambdaQuery()
                .eq(Message::getSessionId, ticket.getSessionId())
                .orderByDesc(Message::getCreateTime)
                .orderByDesc(Message::getId)
                .last("LIMIT 10"));
        Collections.reverse(messages);
        detail.setMessages(messages.stream().map(m -> {
            TicketDetailVO.MessageView view = new TicketDetailVO.MessageView();
            view.setType(m.getType());
            view.setContent(m.getContent());
            view.setCreateTime(m.getCreateTime());
            return view;
        }).toList());
        return detail;
    }

    // ─── 管理端写操作 ───

    @Override
    @Transactional(rollbackFor = Exception.class)
    public TicketDetailVO.TicketView updateStatus(String ticketNo, TicketStatusUpdateRequest request,
                                                    Integer operatorId) {
        TicketStatusEnum target = TicketStatusEnum.of(request.getStatus());
        if (target == null) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "目标状态不合法");
        }

        Ticket ticket = getByTicketNo(ticketNo);
        TicketStatusEnum from = ticket.getStatus();
        if (!from.canTransitionTo(target)) {
            throw new BusinessException(BusinessStatusEnum.CONFLICT, "不允许的状态流转");
        }

        LocalDateTime now = LocalDateTime.now();
        ticket.setStatus(target)
                .setUpdateTime(now)
                .setResolvedTime(target == TicketStatusEnum.RESOLVED ? now : ticket.getResolvedTime())
                .setClosedTime(target == TicketStatusEnum.CLOSED ? now : ticket.getClosedTime());
        // 首响以首次状态流转为准；已关闭不构成响应（直接关掉多是无效应答）
        if (ticket.getFirstResponseTime() == null && target == TicketStatusEnum.PROCESSING) {
            ticket.setFirstResponseTime(now);
        }
        updateById(ticket);

        ticketLogMapper.insert(new TicketLog()
                .setTicketId(ticket.getId())
                .setOperatorId(operatorId)
                .setFromStatus(from)
                .setToStatus(target)
                .setRemark(request.getRemark() == null ? "" : request.getRemark())
                .setCreateTime(now));

        // 状态变化写一条 system 消息到来源会话，用户下次打开客服弹窗能看到进展
        appendStatusMessage(ticket, target, request.getRemark(), now);

        log.info("客服工单状态流转: ticketNo={}, {} -> {}, operatorId={}",
                ticketNo, from, target, operatorId);
        return toView(ticket);
    }

    /**
     * 工单状态变更后向来源会话追加一条系统消息。
     * <p>
     * 只写 cs_message，不走 SSE 推送：用户此刻多半不在会话里，写库才能在下次打开时看到。
     * 工单没有来源会话（如后台手工补录）时跳过，不凭空造会话。
     */
    private void appendStatusMessage(Ticket ticket, TicketStatusEnum to, String remark,
                                     LocalDateTime now) {
        if (ticket.getSessionId() == null) {
            return;
        }
        String content = String.format("工单 %s 状态已更新为「%s」。", ticket.getTicketNo(), to.getText());
        if (remark != null && !remark.isBlank()) {
            content += "\n客服备注：" + remark.trim();
        }
        Message message = new Message()
                .setSessionId(ticket.getSessionId())
                .setType(MESSAGE_TYPE_SYSTEM)
                .setContent(content)
                .setCreateTime(now);
        messageMapper.insert(message);
    }

    @Override
    public void updateRemark(String ticketNo, String adminRemark) {
        Ticket ticket = getByTicketNo(ticketNo);
        ticket.setAdminRemark(adminRemark).setUpdateTime(LocalDateTime.now());
        updateById(ticket);
    }

    // ─── helpers ───

    private Ticket getByTicketNo(String ticketNo) {
        Ticket ticket = getOne(Wrappers.<Ticket>lambdaQuery().eq(Ticket::getTicketNo, ticketNo));
        if (ticket == null) {
            throw new BusinessException(BusinessStatusEnum.NOT_FOUND, "工单不存在");
        }
        return ticket;
    }

    private TicketDetailVO.TicketView toView(Ticket ticket) {
        TicketDetailVO.TicketView view = new TicketDetailVO.TicketView();
        view.setTicketNo(ticket.getTicketNo());
        view.setUserId(ticket.getUserId());
        view.setUserName(userNamesOf(List.of(ticket.getUserId())).get(ticket.getUserId()));
        view.setSessionId(ticket.getSessionId());
        view.setSummary(ticket.getSummary());
        view.setDetail(ticket.getDetail());
        view.setAdminRemark(ticket.getAdminRemark());
        view.setNeedsInfo(Integer.valueOf(1).equals(ticket.getNeedsInfo()));
        view.setFirstResponseTime(ticket.getFirstResponseTime());
        view.setResolvedTime(ticket.getResolvedTime());
        view.setClosedTime(ticket.getClosedTime());
        view.setCreateTime(ticket.getCreateTime());
        view.setUpdateTime(ticket.getUpdateTime());
        if (ticket.getCategory() != null) {
            view.setCategory(ticket.getCategory().getCode());
            view.setCategoryText(ticket.getCategory().getText());
        }
        if (ticket.getStatus() != null) {
            view.setStatus(ticket.getStatus().getCode());
            view.setStatusText(ticket.getStatus().getText());
        }
        if (ticket.getPriority() != null) {
            view.setPriority(ticket.getPriority().getCode());
            view.setPriorityText(ticket.getPriority().getText());
        }
        return view;
    }

    /**
     * 按用户 ID 批量取名称；用户已被删除时返回空 map 值，不影响工单本身可读。
     */
    private Map<Integer, String> userNamesOf(List<Integer> userIds) {
        if (userIds.isEmpty()) {
            return Map.of();
        }
        return userMapper.selectBatchIds(userIds).stream()
                .collect(Collectors.toMap(User::getId, User::getName, (a, b) -> a));
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    /**
     * 时间下界：只给日期时取当天 00:00:00。
     */
    private LocalDateTime parseLowerBound(String startTime) {
        if (!hasText(startTime)) {
            return null;
        }
        LocalDateTime parsed = parseDateTime(startTime);
        return parsed != null ? parsed : parseDate(startTime).atStartOfDay();
    }

    /**
     * 时间上界：只给日期时含当天全天（23:59:59）。
     */
    private LocalDateTime parseUpperBound(String endTime) {
        if (!hasText(endTime)) {
            return null;
        }
        LocalDateTime parsed = parseDateTime(endTime);
        return parsed != null ? parsed : parseDate(endTime).atTime(23, 59, 59);
    }

    private LocalDateTime parseDateTime(String value) {
        try {
            return LocalDateTime.parse(value.trim().replace('T', ' '),
                    DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        } catch (DateTimeParseException e) {
            return null;
        }
    }

    private LocalDate parseDate(String value) {
        try {
            return LocalDate.parse(value.trim(), DateTimeFormatter.ofPattern("yyyy-MM-dd"));
        } catch (DateTimeParseException e) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "时间格式不合法，应为 yyyy-MM-dd 或 yyyy-MM-dd HH:mm:ss");
        }
    }

    /**
     * 生成对外工单号 TK-YYYYMMDD-xxxxxx，与自增主键分离。
     * <p>
     * 6 位十六进制随机段在高并发下有小概率碰撞，靠唯一索引兜底并重试。
     */
    private String nextTicketNo(LocalDateTime now) {
        String day = now.format(DAY);
        for (int i = 0; i < TICKET_NO_RETRY; i++) {
            String suffix = String.format("%06X", ThreadLocalRandom.current().nextInt(0x1000000));
            String ticketNo = "TK-" + day + "-" + suffix;
            boolean exists = count(Wrappers.<Ticket>lambdaQuery().eq(Ticket::getTicketNo, ticketNo)) > 0;
            if (!exists) {
                return ticketNo;
            }
        }
        throw new BusinessException(BusinessStatusEnum.SERVER_ERROR.getCode(), "工单号生成失败，请重试");
    }
}
