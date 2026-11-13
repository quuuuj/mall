package com.qiujie.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.service.IService;
import com.qiujie.entity.Order;

import java.util.List;
import java.util.Map;

public interface OrderService extends IService<Order> {

    Order createFromCart(Integer userId, Map<String, Object> params);

    Order buyNow(Integer userId, Map<String, Object> params);

    void pay(Integer userId, Integer id, Integer payMethod);

    List<Order> list(Integer userId);

    List<Order> listByStatus(Integer userId, Integer status);

    Order detail(Integer userId, Integer id);

    /**
     * 按订单号查询当前用户自己的订单（智能客服只读工具使用）。
     * <p>
     * 归属校验在 SQL 层完成：订单不属于该用户时与不存在同样处理，不泄露他人订单是否存在。
     */
    Order detailByOrderSn(Integer userId, String orderSn);

    /**
     * 查询当前用户最近的若干订单（按创建时间倒序）。
     */
    List<Order> listRecent(Integer userId, int limit);

    void delete(Integer userId, Integer id);

    IPage<Order> list(Integer current, Integer size, String orderSn, String userName, String status,
                        String startTime, String endTime);

    Order detail(Integer id);

    void deliver(Integer id);

    void cancel(Integer id);

    void receipt(Integer userId, Integer id);

    void updateRecipient(Integer userId, Integer id, String recipientName, String recipientPhone, String recipientAddress, Integer expressDelivery);

    void batchDeliver(List<Integer> ids);

    void delete(Integer id);

    void batchDelete(List<Integer> ids);
}
