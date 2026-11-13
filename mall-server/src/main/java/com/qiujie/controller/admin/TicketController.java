package com.qiujie.controller.admin;

import cn.dev33.satoken.annotation.SaCheckRole;
import cn.dev33.satoken.stp.StpUtil;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.qiujie.dto.TicketDetail;
import com.qiujie.dto.TicketListItem;
import com.qiujie.dto.TicketRemarkRequest;
import com.qiujie.dto.TicketStatusUpdateRequest;
import com.qiujie.dto.Response;
import com.qiujie.dto.ResponseDTO;
import com.qiujie.service.TicketService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 管理端-客服工单。
 * <p>
 * 路径参数用对外的工单号（{@code TK-YYYYMMDD-xxxxxx}）而不是自增主键，
 * 自增主键不出服务端。
 *
 * @author qiujie
 */
@SaCheckRole("admin")
@RestController("adminTicketController")
@RequestMapping("/admin/ticket")
@RequiredArgsConstructor
@Tag(name = "管理端-客服工单")
public class TicketController {

    private final TicketService ticketService;

    @Operation(summary = "分页查询工单列表")
    @GetMapping
    public ResponseDTO<IPage<TicketListItem>> list(@RequestParam(defaultValue = "1") Integer current,
                                                     @RequestParam(defaultValue = "10") Integer size,
                                                     Integer status, Integer category,
                                                     String startTime, String endTime) {
        return Response.success(ticketService.list(current, size, status, category, startTime, endTime));
    }

    @Operation(summary = "工单详情（含最近 10 条会话片段）")
    @GetMapping("/{ticketNo}")
    public ResponseDTO<TicketDetail> detail(@PathVariable String ticketNo) {
        return Response.success(ticketService.detail(ticketNo));
    }

    @Operation(summary = "改状态（非法流转被拒绝）")
    @PutMapping("/{ticketNo}/status")
    public ResponseDTO<TicketDetail.TicketView> updateStatus(@PathVariable String ticketNo,
                                                                 @Valid @RequestBody TicketStatusUpdateRequest request) {
        return Response.success(ticketService.updateStatus(ticketNo, request, StpUtil.getLoginIdAsInt()));
    }

    @Operation(summary = "写管理员备注")
    @PutMapping("/{ticketNo}/remark")
    public ResponseDTO<Void> updateRemark(@PathVariable String ticketNo,
                                          @Valid @RequestBody TicketRemarkRequest request) {
        ticketService.updateRemark(ticketNo, request.getAdminRemark());
        return Response.ok("备注已保存");
    }
}
