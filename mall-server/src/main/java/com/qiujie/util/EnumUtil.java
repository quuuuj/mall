package com.qiujie.util;


import com.qiujie.enums.DictEnum;

import java.util.*;

public class EnumUtil {

    /**
     * 获取枚举所有项的列表
     *
     * @param enumType 枚举类型
     * @param <T>      DictEnum
     * @return
     */
    public static <T extends DictEnum<?>> List<Map<String, Object>> getEnumList(Class<T> enumType) {
        List<Map<String, Object>> list = new ArrayList<>();
        if (!enumType.isEnum()) {
            return new ArrayList<>();
        }
        T[] enums = enumType.getEnumConstants();
        if (enums == null || enums.length <= 0) {
            return new ArrayList<>();
        }
        for (T enumItem : enums) {
            Map<String, Object> map = new HashMap<>();
            map.put("code", enumItem.getCode());
            map.put("text", enumItem.getText());
            list.add(map);
        }
        return list;
    }


}
