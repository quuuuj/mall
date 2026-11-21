package com.qiujie.enums;



public interface DictEnum<T> extends BaseEnum<T> {
    T getCode();
    String getText();
}
