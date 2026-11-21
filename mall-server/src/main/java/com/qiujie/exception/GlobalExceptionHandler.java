package com.qiujie.exception;

import cn.dev33.satoken.exception.NotLoginException;
import cn.dev33.satoken.exception.SaTokenException;
import com.qiujie.common.Response;
import com.qiujie.enums.BusinessStatusEnum;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseBody;

@ControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger logger = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(SaTokenException.class)
    @ResponseBody
    public Response<?> handleSaToken(SaTokenException e) {
        if (e instanceof NotLoginException) {
            return Response.error(BusinessStatusEnum.UNAUTHORIZED.getCode(), e.getMessage());
        }
        return Response.error(BusinessStatusEnum.FORBIDDEN);
    }

    @ExceptionHandler(BusinessException.class)
    @ResponseBody
    public Response<?> HandleBusinessException(BusinessException exception){
        logger.info(exception.getMessage());
        return Response.error(exception.getCode(),exception.getMessage());
    }
}
