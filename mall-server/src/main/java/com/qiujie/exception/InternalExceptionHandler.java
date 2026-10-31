package com.qiujie.exception;

import com.qiujie.dto.Response;
import com.qiujie.dto.ResponseDTO;
import com.qiujie.enums.BusinessStatusEnum;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.stream.Collectors;

/**
 * 内部命名空间 {@code /internal/**} 专用异常处理。
 * <p>
 * 调用方是另一端服务而不是浏览器，需要真实 HTTP 状态码来区分鉴权失败与参数错误；
 * 与全局 {@link BaseExceptionHandler} 的「业务码放 body、HTTP 一律 200」不同。
 * 只作用于 {@code controller.internal} 包，不影响既有前端接口的响应形态。
 *
 * @author qiujie
 */
@Order(Ordered.HIGHEST_PRECEDENCE)
@RestControllerAdvice(basePackages = "com.qiujie.controller.internal")
public class InternalExceptionHandler {

    private static final Logger logger = LoggerFactory.getLogger(InternalExceptionHandler.class);

    @ExceptionHandler(ServiceException.class)
    public ResponseEntity<ResponseDTO> handleServiceException(ServiceException e) {
        HttpStatus status = switch (e.getCode()) {
            case 400 -> HttpStatus.BAD_REQUEST;
            case 403, 1300 -> HttpStatus.FORBIDDEN;
            case 401, 1200 -> HttpStatus.UNAUTHORIZED;
            case 404 -> HttpStatus.NOT_FOUND;
            default -> HttpStatus.OK;
        };
        logger.info("内部接口拒绝: code={}, message={}", e.getCode(), e.getMessage());
        return ResponseEntity.status(status).body(Response.error(e.getCode(), e.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ResponseDTO> handleValidation(MethodArgumentNotValidException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
                .map(err -> err.getField() + ": " + err.getDefaultMessage())
                .collect(Collectors.joining("; "));
        return ResponseEntity.badRequest().body(Response.error(400, msg));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ResponseDTO> handleException(Exception e) {
        logger.error("内部接口未处理异常", e);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Response.error(BusinessStatusEnum.ERROR));
    }
}
