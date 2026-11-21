package com.qiujie.service.impl;

import cn.dev33.satoken.stp.StpUtil;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.qiujie.entity.User;
import com.qiujie.common.ValidateCode;
import com.qiujie.enums.BusinessStatusEnum;
import com.qiujie.enums.UserStatusEnum;
import com.qiujie.exception.BusinessException;
import com.qiujie.mapper.UserMapper;
import com.qiujie.service.AuthService;
import com.qiujie.util.DeviceUtil;
import com.qiujie.cache.RedisUtil;
import com.qiujie.util.ValidateCodeUtil;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.util.Map;

@Service
public class AuthServiceImpl extends ServiceImpl<UserMapper, User> implements AuthService {

    private final UserMapper userMapper;
    private final PasswordEncoder passwordEncoder;
    private final RedisUtil redisUtil;

    public AuthServiceImpl(UserMapper userMapper, PasswordEncoder passwordEncoder, RedisUtil redisUtil) {
        this.userMapper = userMapper;
        this.passwordEncoder = passwordEncoder;
        this.redisUtil = redisUtil;
    }

    @Override
    public void register(String code, String password, String phone, String verificationCode, String uuid) {
        if (code == null || code.isBlank() || password == null || password.isBlank()) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "用户名和密码不能为空");
        }
        if (uuid == null || uuid.isBlank()) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "验证码不存在");
        }
        String codeInRedis = (String) redisUtil.get("validate:code:" + uuid);
        if (codeInRedis == null) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "验证码不存在");
        }
        if (!codeInRedis.equals(verificationCode)) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "验证码错误");
        }
        redisUtil.del("validate:code:" + uuid);

        User exist = userMapper.selectOne(new QueryWrapper<User>().eq("code", code));
        if (exist != null) {
            throw new BusinessException(BusinessStatusEnum.CONFLICT, "用户名已存在");
        }
        User user = new User();
        user.setCode(code);
        user.setName(code);
        user.setPassword(passwordEncoder.encode(password));
        user.setPhone(phone);
        user.setStatus(UserStatusEnum.ENABLED);
        userMapper.insert(user);
    }

    @Override
    public Map<String, Object> login(String code, String password, String verificationCode, String uuid, String pathPrefix, HttpServletRequest request) {
        if (uuid == null || uuid.isBlank()) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "验证码不存在");
        }
        String codeInRedis = (String) redisUtil.get("validate:code:" + uuid);
        if (codeInRedis == null) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "验证码不存在");
        }
        if (!codeInRedis.equals(verificationCode)) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "验证码错误");
        }
        redisUtil.del("validate:code:" + uuid);

        User existUser = userMapper.selectOne(new QueryWrapper<User>().eq("code", code));
        if (existUser == null) {
            throw new BusinessException(BusinessStatusEnum.LOGIN_FAILED);
        }
        if (existUser.getStatus() == UserStatusEnum.DISABLED) {
            throw new BusinessException(BusinessStatusEnum.FORBIDDEN, "账号已被禁用");
        }
        if (!passwordEncoder.matches(password, existUser.getPassword())) {
            throw new BusinessException(BusinessStatusEnum.LOGIN_FAILED);
        }

        String role = pathPrefix.startsWith("/admin") ? "admin" : "portal";
        String device = DeviceUtil.getRequestDevice(request);
        StpUtil.login(existUser.getId(), role + ":" + device);
        StpUtil.getSession().set("device", device);
        StpUtil.getSession().set("user", existUser);

        return Map.of("user", existUser, "token", StpUtil.getTokenValue());
    }

    @Override
    public Map<String, Object> getVerificationCode() {
        ValidateCode validateCode = ValidateCodeUtil.generateValidateCode();
        String uuid = java.util.UUID.randomUUID().toString().replace("-", "");
        redisUtil.set("validate:code:" + uuid, validateCode.getCode(), 60);
        return Map.of("uuid", uuid, "image", validateCode.getImage());
    }

    @Override
    public void logout(String token, String requestUri) {
        StpUtil.logout();
    }
}
