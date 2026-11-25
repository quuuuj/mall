package com.qiujie.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.qiujie.entity.User;
import org.apache.ibatis.annotations.Param;

import java.util.List;

public interface UserMapper extends BaseMapper<User> {

    User queryByCode(@Param("code") String code);

    User queryInfo(@Param("id") Integer id);

    List<User> queryUserDeptVO();
}
