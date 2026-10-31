package com.qiujie.controller.internal;

import com.qiujie.dto.CsTicketCreateRequest;
import com.qiujie.dto.CsTicketCreateResponse;
import com.qiujie.dto.Response;
import com.qiujie.dto.ResponseDTO;
import com.qiujie.service.CsTicketService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 内部接口 — 仅供 mall-customer 通过共享密钥调用
 * <p>
 * 挂在 {@code /internal/**} 而不是 {@code /admin/**}，避免在 Sa-Token 登录拦截里
 * 开豁免口；该命名空间由 {@code InternalTokenInterceptor} 校验
 * {@code X-Internal-Token}，不暴露给任何前端。
 *
 * @author qiujie
 */
@RestController
@RequestMapping("/internal")
@RequiredArgsConstructor
@Tag(name = "内部接口(不对外)")
public class InternalTicketController {

    private final CsTicketService csTicketService;

    @Operation(summary = "客服建单（Python 调用）")
    @PostMapping("/cs-ticket")
    public ResponseDTO<CsTicketCreateResponse> createTicket(@Valid @RequestBody CsTicketCreateRequest request) {
        return Response.success(csTicketService.create(request));
    }
}
