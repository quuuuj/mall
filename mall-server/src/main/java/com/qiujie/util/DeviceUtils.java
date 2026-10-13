package com.qiujie.util;

import cn.hutool.http.useragent.Platform;
import cn.hutool.http.useragent.UserAgent;
import cn.hutool.http.useragent.UserAgentUtil;
import jakarta.servlet.http.HttpServletRequest;

/**
 * 设备类型识别工具 —— 从 User-Agent 解析客户端设备类型
 *
 * @author qiujie
 */
public class DeviceUtils {

    private DeviceUtils() {}

    /**
     * 从请求中解析设备类型
     * @return "pc" / "mobile" / "pad" / "miniProgram"
     */
    public static String getRequestDevice(HttpServletRequest request) {
        if (request == null) return "pc";
        String ua = request.getHeader("User-Agent");
        if (ua == null || ua.isBlank()) return "pc";

        if (isMiniProgram(ua)) return "miniProgram";
        if (isPad(ua)) return "pad";

        // 只按运行平台判定，不能用 UserAgent#isMobile()：后者把 MicroMessenger、DingTalk
        // 等"移动端浏览器"也算作 mobile，会导致 PC 版微信/企业微信/钉钉的内置浏览器被误判为手机
        UserAgent parsed = UserAgentUtil.parse(ua);
        if (parsed == null) return "pc";
        Platform platform = parsed.getPlatform();
        return platform != null && platform.isMobile() ? "mobile" : "pc";
    }

    private static boolean isMiniProgram(String ua) {
        return ua.toLowerCase().contains("micromessenger")
                && ua.toLowerCase().contains("miniprogram");
    }

    private static boolean isPad(String ua) {
        String lower = ua.toLowerCase();
        if (lower.contains("ipad")) return true;
        return lower.contains("android") && !lower.contains("mobile");
    }
}
