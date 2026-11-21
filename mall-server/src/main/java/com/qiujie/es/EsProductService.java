package com.qiujie.es;

import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.qiujie.entity.Product;
import com.qiujie.entity.ProductImg;
import com.qiujie.enums.ProductStatusEnum;
import com.qiujie.mapper.ProductImgMapper;
import com.qiujie.mapper.ProductMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 商品 ES 服务 — 索引写入 + 搜索/推荐（ES 优先，失败降级 MySQL）
 *
 * @author qiujie
 */
@Service
public class EsProductService {

    private static final Logger log = LoggerFactory.getLogger(EsProductService.class);

    private final ProductMapper productMapper;
    private final ProductImgMapper productImgMapper;

    @Autowired(required = false)
    private ProductSearchRepository productSearchRepository;

    @Autowired(required = false)
    private ElasticsearchOperations esOperations;

    public EsProductService(ProductMapper productMapper, ProductImgMapper productImgMapper) {
        this.productMapper = productMapper;
        this.productImgMapper = productImgMapper;
    }

    /**
     * 批量同步商品到 ES，定时增量补偿使用
     */
    public void indexBatch(List<Product> products) {
        if (productSearchRepository == null || products.isEmpty()) return;
        try {
            Map<Integer, String> imgMap = batchProductImages(products);
            List<ProductDocument> docs = products.stream()
                    .filter(p -> p.getStatus() == ProductStatusEnum.ON_SHELF)
                    .map(p -> buildDocument(p, imgMap.get(p.getId())))
                    .toList();
            if (!docs.isEmpty()) {
                productSearchRepository.saveAll(docs);
            }
        } catch (Exception e) {
            log.warn("ES 批量索引失败: {}", e.getMessage());
        }
    }

    public Map<String, Object> search(String keyword, Integer current, Integer size) {
        if (keyword == null || keyword.trim().isEmpty()) return null;
        try {
            return searchFromEs(keyword, current, size);
        } catch (Exception e) {
            log.warn("ES 搜索失败，降级为 MySQL LIKE 查询: {}", e.getMessage());
            return searchFromMysql(keyword, current, size);
        }
    }

    private Map<String, Object> searchFromEs(String keyword, Integer current, Integer size) {
        if (esOperations == null) throw new RuntimeException("ES not available");
        int pageNum = current != null ? current - 1 : 0;
        int pageSize = size != null ? size : 10;

        Query esQuery = Query.of(q -> q
                .bool(b -> b
                        .filter(f -> f.term(t -> t.field("status")
                                .value(v -> v.longValue(ProductStatusEnum.ON_SHELF.getCode()))))
                        .should(s -> s.match(m -> m.field("name").query(keyword.trim())))
                        .should(s -> s.match(m -> m.field("detail").query(keyword.trim())))
                        .minimumShouldMatch("1")));

        var nativeQuery = NativeQuery.builder()
                .withQuery(esQuery)
                .withPageable(PageRequest.of(pageNum, pageSize, Sort.by(Sort.Order.desc("_score"))))
                .build();

        SearchHits<ProductDocument> hits = esOperations.search(nativeQuery, ProductDocument.class);

        Map<String, Object> data = new HashMap<>();
        data.put("records", hits.getSearchHits().stream().map(h -> h.getContent()).toList());
        data.put("total", hits.getTotalHits());
        data.put("current", current != null ? current : 1);
        data.put("size", pageSize);
        return data;
    }

    private Map<String, Object> searchFromMysql(String keyword, Integer current, Integer size) {
        Page<Product> page = new Page<>(current != null ? current : 1, size != null ? size : 10);
        var result = productMapper.selectPageByKeyword(page, keyword.trim());
        Map<String, Object> data = new HashMap<>();
        data.put("records", result.getRecords());
        data.put("total", result.getTotal());
        data.put("current", result.getCurrent());
        data.put("size", result.getSize());
        data.put("productImages", batchProductImages(result.getRecords()));
        return data;
    }

    public List<ProductDocument> recommend(Integer productId, Integer size) {
        int limit = size != null ? size : 8;
        try {
            if (esOperations != null) {
                ProductDocument source = esOperations.get(
                        String.valueOf(productId), ProductDocument.class);
                if (source != null) {
                    var query = Query.of(q -> q.bool(b -> b
                            .mustNot(mn -> mn.term(t -> t.field("id")
                                    .value(v -> v.longValue(productId))))
                            .filter(f -> f.term(t -> t.field("status")
                                    .value(v -> v.longValue(ProductStatusEnum.ON_SHELF.getCode()))))
                            .should(s -> s.match(m -> m.field("name")
                                    .query(source.getName()).boost(3.0f)))
                            .should(s -> s.term(t -> t.field("categoryId")
                                    .value(v -> v.longValue(source.getCategoryId())).boost(5.0f)))
                            .minimumShouldMatch("1")));
                    return esOperations.search(
                            NativeQuery.builder().withQuery(query).withMaxResults(limit)
                                    .withSort(Sort.by(Sort.Order.desc("_score"))).build(),
                            ProductDocument.class)
                            .getSearchHits().stream().map(h -> h.getContent()).toList();
                }
            }
        } catch (Exception e) {
            log.warn("ES 推荐失败，降级为 MySQL 同类目查询: {}", e.getMessage());
        }
        // 降级：MySQL 同类目商品（排除当前商品）
        Product product = productMapper.selectById(productId);
        if (product == null || product.getCategoryId() == null) return List.of();
        List<Product> products = productMapper.selectByCategoryIdLimit(product.getCategoryId(), limit + 1);
        List<Product> candidates = products.stream()
                .filter(p -> !p.getId().equals(productId))
                .limit(limit)
                .toList();
        Map<Integer, String> imgMap = batchProductImages(candidates);
        return candidates.stream()
                .map(p -> buildDocument(p, imgMap.get(p.getId())))
                .toList();
    }

    private ProductDocument buildDocument(Product product, String imageUrl) {
        ProductDocument doc = new ProductDocument();
        doc.setId(product.getId());
        doc.setName(product.getName());
        doc.setDetail(product.getDetail());
        doc.setPrice(product.getPrice());
        doc.setStock(product.getStock());
        doc.setCategoryId(product.getCategoryId());
        doc.setStatus(product.getStatus() != null ? product.getStatus().getCode() : 0);
        doc.setCreateTime(product.getCreateTime() != null ? product.getCreateTime().toString() : null);
        if (imageUrl != null) {
            doc.setImage(imageUrl);
        }
        return doc;
    }

    private Map<Integer, String> batchProductImages(List<Product> products) {
        if (products == null || products.isEmpty()) return Collections.emptyMap();
        List<Integer> productIds = products.stream().map(Product::getId).distinct().toList();
        return productImgMapper.selectByProductIds(productIds).stream()
                .collect(Collectors.toMap(ProductImg::getProductId, ProductImg::getUrl, (a, b) -> a));
    }
}
