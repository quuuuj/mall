package com.qiujie.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.qiujie.entity.Order;
import com.qiujie.vo.CategorySalesVO;
import org.apache.ibatis.annotations.Param;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

public interface OrderMapper extends BaseMapper<Order> {

    List<Order> selectByUserId(@Param("userId") Integer userId);

    Order selectDetailById(@Param("id") Integer id);

    IPage<Order> selectPageWithParams(Page<Order> page,
                                        @Param("orderSn") String orderSn,
                                        @Param("userName") String userName,
                                        @Param("statusList") List<Integer> statusList,
                                        @Param("startTime") String startTime,
                                        @Param("endTime") String endTime);

    List<Map<String, Object>> selectTrendData(@Param("days") Integer days);

    List<CategorySalesVO> selectCategorySales();

    /** 聚合查询指定时间范围内的订单数和销售总额，避免拉全量数据到内存 */
    Map<String, Object> selectDailyStats(@Param("start") LocalDateTime start, @Param("end") LocalDateTime end);
}
