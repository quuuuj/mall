package com.qiujie.controller.admin;

import cn.dev33.satoken.annotation.SaCheckRole;
import cn.dev33.satoken.stp.StpUtil;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.qiujie.dto.ChunkEnabledRequest;
import com.qiujie.dto.ChunkUpdateRequest;
import com.qiujie.dto.FaqRequest;
import com.qiujie.vo.KnowledgeChunkVO;
import com.qiujie.dto.KnowledgeDocUpdateRequest;
import com.qiujie.common.Response;
import com.qiujie.entity.Faq;
import com.qiujie.entity.KnowledgeChangeLog;
import com.qiujie.entity.KnowledgeDoc;
import com.qiujie.entity.RetrievalTest;
import com.qiujie.service.KnowledgeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 管理端-知识库管理（文档 / FAQ / 检索测试）。
 *
 * @author qiujie
 */
@SaCheckRole("admin")
@RestController
@RequestMapping("/admin/knowledge")
@RequiredArgsConstructor
@Tag(name = "管理端-知识库管理")
public class KnowledgeController {

    private final KnowledgeService knowledgeService;

    // ─── 文档 ───

    @Operation(summary = "上传文档（异步触发解析入库）")
    @PostMapping(value = "/doc/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Response<KnowledgeDoc> upload(@RequestParam("file") org.springframework.web.multipart.MultipartFile file,
                                            @RequestParam(required = false) String category,
                                            @RequestParam(required = false) String tags) {
        return Response.success(knowledgeService.upload(file, category, tags, StpUtil.getLoginIdAsInt()));
    }

    @Operation(summary = "文档列表")
    @GetMapping("/doc")
    public Response<IPage<KnowledgeDoc>> listDocs(@RequestParam(defaultValue = "1") Integer current,
                                                      @RequestParam(defaultValue = "10") Integer size,
                                                      String category, String tags, String status, Integer enabled) {
        return Response.success(knowledgeService.listDocs(current, size, category, tags, status, enabled));
    }

    @Operation(summary = "文档详情")
    @GetMapping("/doc/{id}")
    public Response<KnowledgeDoc> docDetail(@PathVariable Long id) {
        return Response.success(knowledgeService.docDetail(id));
    }

    @Operation(summary = "编辑文档元数据与处理参数")
    @PutMapping("/doc/{id}")
    public Response<Void> updateDoc(@PathVariable Long id, @Valid @RequestBody KnowledgeDocUpdateRequest request) {
        knowledgeService.updateDoc(id, request, StpUtil.getLoginIdAsInt());
        return Response.ok("已保存");
    }

    @Operation(summary = "删除文档")
    @DeleteMapping("/doc/{id}")
    public Response<Void> deleteDoc(@PathVariable Long id) {
        knowledgeService.deleteDoc(id, StpUtil.getLoginIdAsInt());
        return Response.ok("已删除");
    }

    @Operation(summary = "启停文档")
    @PutMapping("/doc/{id}/toggle")
    public Response<Void> toggleDoc(@PathVariable Long id) {
        knowledgeService.toggleDoc(id, StpUtil.getLoginIdAsInt());
        return Response.ok("已切换");
    }

    @Operation(summary = "重试处理文档")
    @PostMapping("/doc/{id}/retry")
    public Response<Void> retryDoc(@PathVariable Long id) {
        knowledgeService.retryDoc(id, StpUtil.getLoginIdAsInt());
        return Response.ok("已重新处理");
    }

    @Operation(summary = "全量重建向量")
    @PostMapping("/rebuild")
    public Response<Void> rebuild() {
        knowledgeService.rebuild(StpUtil.getLoginIdAsInt());
        return Response.ok("已触发重建");
    }

    @Operation(summary = "变更记录")
    @GetMapping("/change-log")
    public Response<IPage<KnowledgeChangeLog>> changeLogs(@RequestParam(defaultValue = "1") Integer current,
                                                              @RequestParam(defaultValue = "10") Integer size,
                                                              String targetType) {
        return Response.success(knowledgeService.changeLogs(current, size, targetType));
    }

    // ─── 单块编辑（改动只落 Qdrant，重建会覆盖） ───

    @Operation(summary = "文档分块列表")
    @GetMapping("/doc/{id}/chunks")
    public Response<List<KnowledgeChunkVO>> listChunks(@PathVariable Long id) {
        return Response.success(knowledgeService.listChunks(id));
    }

    @Operation(summary = "编辑切片正文（立即重算向量）")
    @PutMapping("/doc/{id}/chunks/{chunkIndex}")
    public Response<Void> updateChunk(@PathVariable Long id, @PathVariable Integer chunkIndex,
                                         @Valid @RequestBody ChunkUpdateRequest request) {
        knowledgeService.updateChunk(id, chunkIndex, request.getContent(), StpUtil.getLoginIdAsInt());
        return Response.ok("已保存");
    }

    @Operation(summary = "启停切片")
    @PutMapping("/doc/{id}/chunks/{chunkIndex}/enabled")
    public Response<Void> setChunkEnabled(@PathVariable Long id, @PathVariable Integer chunkIndex,
                                              @Valid @RequestBody ChunkEnabledRequest request) {
        knowledgeService.setChunkEnabled(id, chunkIndex, Boolean.TRUE.equals(request.getEnabled()),
                StpUtil.getLoginIdAsInt());
        return Response.ok("已切换");
    }

    @Operation(summary = "删除切片")
    @DeleteMapping("/doc/{id}/chunks/{chunkIndex}")
    public Response<Void> deleteChunk(@PathVariable Long id, @PathVariable Integer chunkIndex) {
        knowledgeService.deleteChunk(id, chunkIndex, StpUtil.getLoginIdAsInt());
        return Response.ok("已删除");
    }

    // ─── FAQ ───

    @Operation(summary = "FAQ 列表")
    @GetMapping("/faq")
    public Response<IPage<Faq>> listFaqs(@RequestParam(defaultValue = "1") Integer current,
                                             @RequestParam(defaultValue = "10") Integer size,
                                             String category, Integer enabled) {
        return Response.success(knowledgeService.listFaqs(current, size, category, enabled));
    }

    @Operation(summary = "FAQ 详情")
    @GetMapping("/faq/{id}")
    public Response<Faq> faqDetail(@PathVariable Long id) {
        return Response.success(knowledgeService.faqDetail(id));
    }

    @Operation(summary = "新增 FAQ")
    @PostMapping("/faq")
    public Response<Long> addFaq(@Valid @RequestBody FaqRequest request) {
        return Response.success(knowledgeService.addFaq(request, StpUtil.getLoginIdAsInt()));
    }

    @Operation(summary = "编辑 FAQ")
    @PutMapping("/faq/{id}")
    public Response<Void> updateFaq(@PathVariable Long id, @Valid @RequestBody FaqRequest request) {
        knowledgeService.updateFaq(id, request, StpUtil.getLoginIdAsInt());
        return Response.ok("已保存");
    }

    @Operation(summary = "删除 FAQ")
    @DeleteMapping("/faq/{id}")
    public Response<Void> deleteFaq(@PathVariable Long id) {
        knowledgeService.deleteFaq(id, StpUtil.getLoginIdAsInt());
        return Response.ok("已删除");
    }

    @Operation(summary = "启停 FAQ")
    @PutMapping("/faq/{id}/toggle")
    public Response<Void> toggleFaq(@PathVariable Long id) {
        knowledgeService.toggleFaq(id, StpUtil.getLoginIdAsInt());
        return Response.ok("已切换");
    }

    // ─── 检索测试 ───

    @Operation(summary = "检索测试（调 Python + 落库）")
    @PostMapping("/test")
    public Response<Map<String, Object>> testRetrieval(@Valid @RequestBody com.qiujie.dto.RetrievalTestRequest request) {
        return Response.success(knowledgeService.testRetrieval(request.getQuery(), request.getParams(),
                StpUtil.getLoginIdAsInt()));
    }

    @Operation(summary = "检索测试历史")
    @GetMapping("/test/history")
    public Response<IPage<RetrievalTest>> testHistory(@RequestParam(defaultValue = "1") Integer current,
                                                          @RequestParam(defaultValue = "10") Integer size) {
        return Response.success(knowledgeService.testHistory(current, size));
    }
}
