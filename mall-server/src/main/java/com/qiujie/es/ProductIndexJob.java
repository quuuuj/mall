package com.qiujie.es;

import com.qiujie.entity.Product;
import com.qiujie.mapper.ProductMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.List;

/**
 * ES 商品索引定时任务 — 每分钟扫描 MySQL 最近变更的商品批量写入 ES
 *
 * @author qiujie
 */
@Component
public class ProductIndexJob {

    private static final Logger log = LoggerFactory.getLogger(ProductIndexJob.class);

    private final ProductMapper productMapper;
    private final EsProductService esProductService;

    public ProductIndexJob(ProductMapper productMapper, EsProductService esProductService) {
        this.productMapper = productMapper;
        this.esProductService = esProductService;
    }

    /**
     * 每分钟扫描最近 2 分钟 update_time 变更的商品，批量写入 ES 索引
     */
    @Scheduled(fixedRate = 60_000)
    public void indexRecentProducts() {
        try {
            LocalDateTime since = LocalDateTime.now().minusMinutes(2);
            List<Product> products = productMapper.selectByUpdateTime(since);
            if (!products.isEmpty()) {
                esProductService.indexBatch(products);
                log.debug("ES 增量索引完成: {} 个商品", products.size());
            }
        } catch (Exception e) {
            log.warn("ES 增量索引异常: {}", e.getMessage());
        }
    }
}
