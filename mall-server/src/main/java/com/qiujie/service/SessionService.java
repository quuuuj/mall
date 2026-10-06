package com.qiujie.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.qiujie.entity.Session;

import java.util.List;

public interface SessionService extends IService<Session> {

    List<Session> listUserSessions(Integer userId);

    Session create(Integer userId);

    void delete(Long sessionId, Integer userId);
}
