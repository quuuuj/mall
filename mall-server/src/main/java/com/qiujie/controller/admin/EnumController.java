package com.qiujie.controller.admin;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.qiujie.common.Response;
import com.qiujie.enums.*;
import com.qiujie.util.EnumUtil;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/admin/enum")
@Tag(name = "管理端-枚举")
@SaCheckRole("admin")
public class EnumController {

    @Operation(summary = "获取所有枚举选项（用于前端下拉框）")
    @GetMapping("/enums")
    public Response<Map<String, List<Map<String, Object>>>> getEnums() {
        Map<String, List<Map<String, Object>>> result = new HashMap<>();
        result.put("gender", EnumUtil.getEnumList(GenderEnum.class));
        result.put("userStatus", EnumUtil.getEnumList(UserStatusEnum.class));
        result.put("productStatus", EnumUtil.getEnumList(ProductStatusEnum.class));
        result.put("orderStatus", EnumUtil.getEnumList(OrderStatusEnum.class));
        result.put("payMethod", EnumUtil.getEnumList(PayMethodEnum.class));
        result.put("knowledgeStatus", EnumUtil.getEnumList(KnowledgeStatusEnum.class));
        return Response.success(result);
    }
}
