package com.qiujie.service.impl;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.qiujie.dto.CsTicketCreateRequest;
import com.qiujie.dto.CsTicketCreateResponse;
import com.qiujie.entity.CsTicket;
import com.qiujie.entity.CsTicketLog;
import com.qiujie.enums.BusinessStatusEnum;
import com.qiujie.enums.CsTicketCategoryEnum;
import com.qiujie.enums.CsTicketPriorityEnum;
import com.qiujie.enums.CsTicketStatusEnum;
import com.qiujie.exception.ServiceException;
import com.qiujie.mapper.CsTicketLogMapper;
import com.qiujie.mapper.CsTicketMapper;
import com.qiujie.service.CsTicketService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ThreadLocalRandom;

/**
 * 客服工单服务实现
 * <p>
 * 建单与日志在同一事务内写入；工单号与自增主键分离，对外只暴露工单号。
 *
 * @author qiujie
 */
@Slf4j
@Service
public class CsTicketServiceImpl extends ServiceImpl<CsTicketMapper, CsTicket> implements CsTicketService {

    private static final DateTimeFormatter DAY = DateTimeFormatter.ofPattern("yyyyMMdd");
    private static final int TICKET_NO_RETRY = 5;
    private static final int SYSTEM_OPERATOR = 0;

    /**
     * 四类工单的必填字段（detail JSON 的 key）。needsInfo=1 时不做校验：
     * 两轮追问后仍缺字段也要能建单，否则用户诉求无出口。
     */
    private static final Map<CsTicketCategoryEnum, List<String>> REQUIRED_FIELDS = Map.of(
            CsTicketCategoryEnum.REFUND_RETURN, List.of("orderNo", "reason", "received"),
            CsTicketCategoryEnum.LOGISTICS, List.of("orderNo", "phenomenon"),
            CsTicketCategoryEnum.INVOICE, List.of("orderNo", "title", "taxNo"),
            CsTicketCategoryEnum.COMPLAINT, List.of("description")
    );

    /**
     * 各类工单的默认优先级
     */
    private static final Map<CsTicketCategoryEnum, CsTicketPriorityEnum> DEFAULT_PRIORITY = Map.of(
            CsTicketCategoryEnum.REFUND_RETURN, CsTicketPriorityEnum.MEDIUM,
            CsTicketCategoryEnum.LOGISTICS, CsTicketPriorityEnum.MEDIUM,
            CsTicketCategoryEnum.INVOICE, CsTicketPriorityEnum.LOW,
            CsTicketCategoryEnum.COMPLAINT, CsTicketPriorityEnum.HIGH
    );

    private final CsTicketLogMapper csTicketLogMapper;

    public CsTicketServiceImpl(CsTicketLogMapper csTicketLogMapper) {
        this.csTicketLogMapper = csTicketLogMapper;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public CsTicketCreateResponse create(CsTicketCreateRequest request) {
        CsTicketCategoryEnum category = CsTicketCategoryEnum.of(request.getCategory());
        if (category == null) {
            throw new ServiceException(400, "工单类型不合法");
        }

        CsTicketPriorityEnum priority = resolvePriority(request, category);
        boolean needsInfo = Integer.valueOf(1).equals(request.getNeedsInfo());

        JSONObject detail = parseDetail(request.getDetail());
        if (!needsInfo) {
            assertRequiredFields(category, detail);
        }

        LocalDateTime now = LocalDateTime.now();
        CsTicket ticket = new CsTicket()
                .setTicketNo(nextTicketNo(now))
                .setUserId(request.getUserId())
                .setSessionId(request.getSessionId())
                .setCategory(category)
                .setStatus(CsTicketStatusEnum.PENDING)
                .setPriority(priority)
                .setSummary(request.getSummary())
                .setDetail(detail == null ? null : detail.toJSONString())
                .setAdminRemark("")
                .setNeedsInfo(needsInfo ? 1 : 0)
                .setCreateTime(now)
                .setUpdateTime(now);
        save(ticket);

        // 建单日志：from_status 为空，操作人记为系统
        csTicketLogMapper.insert(new CsTicketLog()
                .setTicketId(ticket.getId())
                .setOperatorId(SYSTEM_OPERATOR)
                .setFromStatus(null)
                .setToStatus(CsTicketStatusEnum.PENDING)
                .setRemark("建单")
                .setCreateTime(now));

        log.info("客服工单已创建: ticketNo={}, userId={}, sessionId={}, category={}, needsInfo={}",
                ticket.getTicketNo(), ticket.getUserId(), ticket.getSessionId(), category, needsInfo);

        return new CsTicketCreateResponse(
                ticket.getTicketNo(),
                category.getMessage(),
                CsTicketStatusEnum.PENDING.getMessage(),
                now);
    }

    private CsTicketPriorityEnum resolvePriority(CsTicketCreateRequest request, CsTicketCategoryEnum category) {
        if (request.getPriority() == null) {
            return DEFAULT_PRIORITY.get(category);
        }
        CsTicketPriorityEnum priority = CsTicketPriorityEnum.of(request.getPriority());
        if (priority == null) {
            throw new ServiceException(400, "工单优先级不合法");
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
            throw new ServiceException(400, "工单结构化字段不是合法 JSON");
        }
    }

    private void assertRequiredFields(CsTicketCategoryEnum category, JSONObject detail) {
        List<String> required = REQUIRED_FIELDS.getOrDefault(category, List.of());
        if (required.isEmpty()) {
            return;
        }
        Set<String> present = detail == null ? Set.of() : detail.keySet();
        List<String> missing = required.stream().filter(key -> !present.contains(key)).toList();
        if (!missing.isEmpty()) {
            throw new ServiceException(400, "缺少必填字段: " + String.join(", ", missing));
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
            boolean exists = count(Wrappers.<CsTicket>lambdaQuery().eq(CsTicket::getTicketNo, ticketNo)) > 0;
            if (!exists) {
                return ticketNo;
            }
        }
        throw new ServiceException(BusinessStatusEnum.ERROR.getCode(), "工单号生成失败，请重试");
    }
}
