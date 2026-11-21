package com.qiujie.exception;

import com.qiujie.enums.BusinessStatusEnum;
import lombok.Getter;

/**
 * 自定义异常
 * @author
 * @date
 */
@Getter
public class BusinessException extends RuntimeException {
    private final int code;

    public BusinessException(int code, String message){
        super(message);
        this.code = code;
    }

    public BusinessException(BusinessStatusEnum e){
        super(e.getMessage());
        this.code = e.getCode();
    }

    public BusinessException(BusinessStatusEnum e, String message){
        super(message);
        this.code = e.getCode();
    }


}
