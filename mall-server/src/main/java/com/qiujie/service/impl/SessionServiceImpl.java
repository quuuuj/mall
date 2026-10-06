package com.qiujie.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.qiujie.entity.Session;
import com.qiujie.exception.ServiceException;
import com.qiujie.mapper.SessionMapper;
import com.qiujie.service.SessionService;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class SessionServiceImpl extends ServiceImpl<SessionMapper, Session> implements SessionService {

    @Override
    public List<Session> listUserSessions(Integer userId) {
        return lambdaQuery()
                .eq(Session::getUserId, userId)
                .orderByDesc(Session::getUpdateTime)
                .list();
    }

    @Override
    public Session create(Integer userId) {
        Session session = new Session();
        session.setUserId(userId);
        session.setTitle("新对话");
        save(session);
        return session;
    }

    @Override
    public void delete(Long sessionId, Integer userId) {
        Session session = getById(sessionId);
        if (session == null || !session.getUserId().equals(userId)) {
            throw new ServiceException(403, "无权操作该会话或会话不存在");
        }
        removeById(sessionId);
    }
}
