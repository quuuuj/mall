package com.qiujie.controller.portal;

import com.qiujie.es.ProductDocument;
import com.qiujie.common.Response;
import com.qiujie.entity.Category;
import com.qiujie.entity.Product;
import com.qiujie.service.ImageService;
import com.qiujie.es.EsProductService;
import com.qiujie.service.ProductViewService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.*;

import java.util.List;

import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Map;

@RestController("portalProductController")
@RequestMapping("/portal/product")
@Tag(name = "门户端-商品")
public class ProductController {

    private final ProductViewService productViewService;
    private final EsProductService esProductService;
    private final ImageService imageService;

    public ProductController(ProductViewService productViewService,
                             EsProductService esProductService,
                             ImageService imageService) {
        this.productViewService = productViewService;
        this.esProductService = esProductService;
        this.imageService = imageService;
    }

    @Operation(summary = "首页数据")
    @GetMapping("/home")
    public Response<List<Map<String, Object>>> home() {
        return Response.success(productViewService.home());
    }

    @Operation(summary = "分类列表")
    @GetMapping("/categories")
    public Response<List<Category>> categories() {
        return Response.success(productViewService.categories());
    }

    @Operation(summary = "按分类查询商品")
    @GetMapping("/category/{id}")
    public Response<Map<String, Object>> getByCategory(@PathVariable Integer id,
                                                           @RequestParam(defaultValue = "1") Integer current,
                                                           @RequestParam(defaultValue = "10") Integer size) {
        return Response.success(productViewService.getByCategory(id, current, size));
    }

    @Operation(summary = "搜索商品")
    @GetMapping("/search")
    public Response<Map<String, Object>> search(@RequestParam String keyword,
                                                    @RequestParam(defaultValue = "1") Integer current,
                                                    @RequestParam(defaultValue = "10") Integer size) {
        var result = esProductService.search(keyword, current, size);
        if (result == null) {
            return Response.success();
        }
        return Response.success(result);
    }

    @Operation(summary = "商品详情")
    @GetMapping("/detail/{id}")
    public Response<Product> detail(@PathVariable Integer id) {
        return Response.success(productViewService.detail(id));
    }

    @Operation(summary = "商品推荐（看了又看）")
    @GetMapping("/recommend/{id}")
    public Response<List<ProductDocument>> recommend(@PathVariable Integer id,
                                                         @RequestParam(defaultValue = "8") Integer size) {
        return Response.success(esProductService.recommend(id, size));
    }

    @Operation(summary = "获取商品图片")
    @GetMapping("/img")
    public void image(@RequestParam("key") String key, HttpServletResponse response) throws IOException {
        imageService.serveProductImage(key, response);
    }

}
