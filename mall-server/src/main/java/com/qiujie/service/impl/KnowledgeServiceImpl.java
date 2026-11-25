package com.qiujie.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.qiujie.dto.FaqRequest;
import com.qiujie.dto.KnowledgeDocUpdateRequest;
import com.qiujie.entity.Faq;
import com.qiujie.entity.KnowledgeChangeLog;
import com.qiujie.entity.KnowledgeDoc;
import com.qiujie.entity.RetrievalTest;
import com.qiujie.enums.BusinessStatusEnum;
import com.qiujie.exception.BusinessException;
import com.qiujie.mapper.FaqMapper;
import com.qiujie.mapper.KnowledgeChangeLogMapper;
import com.qiujie.mapper.KnowledgeDocMapper;
import com.qiujie.mapper.RetrievalTestMapper;
import com.qiujie.service.KnowledgeService;
import com.qiujie.client.KnowledgeAdminClient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * 知识库管理实现。
 *
 * @author qiujie
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KnowledgeServiceImpl extends ServiceImpl<KnowledgeDocMapper, KnowledgeDoc>
        implements KnowledgeService {

    private static final Set<String> ALLOWED_TYPES = Set.of("pdf", "docx", "md", "txt", "html", "htm", "image");
    private static final Set<String> IMAGE_SUFFIXES = Set.of("png", "jpg", "jpeg", "gif", "webp", "bmp");

    private final FaqMapper faqMapper;
    private final KnowledgeChangeLogMapper changeLogMapper;
    private final RetrievalTestMapper retrievalTestMapper;
    private final KnowledgeAdminClient knowledgeAdminClient;
    private final ObjectMapper objectMapper;

    @Value("${knowledge.upload-dir:${KNOWLEDGE_UPLOAD_DIR:upload/knowledge/}}")
    private String uploadDir;

    // ─── 文档 ───

    @Override
    @Transactional(rollbackFor = Exception.class)
    public KnowledgeDoc upload(MultipartFile file, String category, String tags, Integer operatorId) {
        String original = file.getOriginalFilename() == null ? "unnamed" : file.getOriginalFilename();
        String suffix = original.contains(".") ? original.substring(original.lastIndexOf(".") + 1).toLowerCase(Locale.ROOT) : "";
        String fileType = IMAGE_SUFFIXES.contains(suffix) ? "image" : suffix;
        if (!ALLOWED_TYPES.contains(fileType)) {
            throw new BusinessException(BusinessStatusEnum.PARAM_ERROR, "不支持的文件类型: " + suffix);
        }

        String storedName = java.util.UUID.randomUUID().toString().replace("-", "") + "." + suffix;
        Path dir = Paths.get(uploadDir).toAbsolutePath().normalize();
        Path target = dir.resolve(storedName);
        try {
            Files.createDirectories(dir);
            // 用 Files.copy 而不是 transferTo：transferTo 传相对路径时，容器/应用上下文
            // 可能把它解析到 servlet 临时目录而非工作目录，导致文件落不到预期位置。
            try (var in = file.getInputStream()) {
                Files.copy(in, target);
            }
        } catch (IOException e) {
            log.error("文件保存失败: {}", target, e);
            throw new BusinessException(BusinessStatusEnum.SERVER_ERROR, "文件保存失败: " + e.getMessage());
        }

        KnowledgeDoc doc = new KnowledgeDoc()
                .setFileName(storedName)
                .setOriginalName(original)
                .setFileType(fileType)
                .setFileSize(file.getSize())
                .setTitle(stripSuffix(original))
                .setCategory(category == null ? "" : category)
                .setTags(tags == null ? "" : tags)
                .setEnabled(1)
                .setStatus("PENDING")
                .setChunkCount(0)
                .setChunkSize(800)
                .setChunkOverlap(100)
                .setCleanRules("{}")
                .setOperatorId(operatorId == null ? 0 : operatorId)
                .setCreateTime(LocalDateTime.now());
        save(doc);
        logChange("DOC", doc.getId(), "CREATE", "上传 " + original, doc.getOperatorId());

        // 异步触发：OCR 大文件可能跑几分钟，不能阻塞上传请求
        knowledgeAdminClient.ingest(doc, target);
        return doc;
    }

    @Override
    public IPage<KnowledgeDoc> listDocs(Integer current, Integer size, String category, String tags,
                                         String status, Integer enabled) {
        LambdaQueryWrapper<KnowledgeDoc> q = new LambdaQueryWrapper<KnowledgeDoc>()
                .like(StringUtils.hasText(category), KnowledgeDoc::getCategory, category)
                .like(StringUtils.hasText(tags), KnowledgeDoc::getTags, tags)
                .eq(StringUtils.hasText(status), KnowledgeDoc::getStatus, status)
                .eq(enabled != null, KnowledgeDoc::getEnabled, enabled)
                .orderByDesc(KnowledgeDoc::getId);
        return page(new Page<>(current, size), q);
    }

    @Override
    public KnowledgeDoc docDetail(Long id) {
        KnowledgeDoc doc = getById(id);
        if (doc == null) {
            throw new BusinessException(BusinessStatusEnum.NOT_FOUND, "文档不存在");
        }
        return doc;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateDoc(Long id, KnowledgeDocUpdateRequest request, Integer operatorId) {
        KnowledgeDoc doc = docDetail(id);
        if (StringUtils.hasText(request.getTitle())) doc.setTitle(request.getTitle());
        if (request.getCategory() != null) doc.setCategory(request.getCategory());
        if (request.getTags() != null) doc.setTags(request.getTags());
        if (request.getChunkSize() != null && request.getChunkSize() >= 100) doc.setChunkSize(request.getChunkSize());
        if (request.getChunkOverlap() != null && request.getChunkOverlap() >= 0) doc.setChunkOverlap(request.getChunkOverlap());
        if (StringUtils.hasText(request.getCleanRules())) doc.setCleanRules(request.getCleanRules());
        doc.setOperatorId(operatorId == null ? 0 : operatorId);
        updateById(doc);
        logChange("DOC", id, "UPDATE", "编辑元数据及处理参数", doc.getOperatorId());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteDoc(Long id, Integer operatorId) {
        docDetail(id);
        removeById(id);
        knowledgeAdminClient.deleteDoc(id);
        logChange("DOC", id, "DELETE", "删除文档", operatorId);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void toggleDoc(Long id, Integer operatorId) {
        KnowledgeDoc doc = docDetail(id);
        int next = Integer.valueOf(1).equals(doc.getEnabled()) ? 0 : 1;
        doc.setEnabled(next);
        doc.setOperatorId(operatorId == null ? 0 : operatorId);
        updateById(doc);
        knowledgeAdminClient.updateDocEnabled(id, next == 1);
        logChange("DOC", id, "TOGGLE", next == 1 ? "启用" : "停用", doc.getOperatorId());
    }

    @Override
    public void retryDoc(Long id, Integer operatorId) {
        KnowledgeDoc doc = docDetail(id);
        doc.setStatus("PENDING");
        doc.setErrorMessage("");
        updateById(doc);
        logChange("DOC", id, "INGEST", "重试处理", operatorId);
        knowledgeAdminClient.ingest(doc, Paths.get(uploadDir, doc.getFileName()));
    }

    @Override
    public void rebuild(Integer operatorId) {
        knowledgeAdminClient.rebuild();
        logChange("REBUILD", 0L, "REBUILD", "全量重建向量", operatorId);
    }

    @Override
    public IPage<KnowledgeChangeLog> changeLogs(Integer current, Integer size, String targetType) {
        return changeLogMapper.selectPage(new Page<>(current, size),
                new LambdaQueryWrapper<KnowledgeChangeLog>()
                        .eq(StringUtils.hasText(targetType), KnowledgeChangeLog::getTargetType, targetType)
                        .orderByDesc(KnowledgeChangeLog::getId));
    }

    // ─── 单块编辑 ───

    @Override
    public List<com.qiujie.vo.KnowledgeChunkVO> listChunks(Long docId) {
        docDetail(docId);
        return knowledgeAdminClient.listChunks(docId);
    }

    @Override
    public void updateChunk(Long docId, Integer chunkIndex, String content, Integer operatorId) {
        docDetail(docId);
        knowledgeAdminClient.updateChunkContent(docId, chunkIndex, content);
        logChange("CHUNK", docId, "UPDATE", "编辑切片 #" + chunkIndex + " 正文", operatorId);
    }

    @Override
    public void setChunkEnabled(Long docId, Integer chunkIndex, boolean enabled, Integer operatorId) {
        docDetail(docId);
        knowledgeAdminClient.updateChunkEnabled(docId, chunkIndex, enabled);
        logChange("CHUNK", docId, "TOGGLE",
                "切片 #" + chunkIndex + (enabled ? " 启用" : " 停用"), operatorId);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteChunk(Long docId, Integer chunkIndex, Integer operatorId) {
        docDetail(docId);
        knowledgeAdminClient.deleteChunk(docId, chunkIndex);
        KnowledgeDoc doc = getById(docId);
        if (doc.getChunkCount() != null && doc.getChunkCount() > 0) {
            doc.setChunkCount(doc.getChunkCount() - 1);
            updateById(doc);
        }
        logChange("CHUNK", docId, "DELETE", "删除切片 #" + chunkIndex, operatorId);
    }

    // ─── FAQ ───

    @Override
    public IPage<Faq> listFaqs(Integer current, Integer size, String category, Integer enabled) {
        return faqMapper.selectPage(new Page<>(current, size),
                new LambdaQueryWrapper<Faq>()
                        .like(StringUtils.hasText(category), Faq::getCategory, category)
                        .eq(enabled != null, Faq::getEnabled, enabled)
                        .orderByDesc(Faq::getId));
    }

    @Override
    public Faq faqDetail(Long id) {
        Faq faq = faqMapper.selectById(id);
        if (faq == null) {
            throw new BusinessException(BusinessStatusEnum.NOT_FOUND, "FAQ 不存在");
        }
        return faq;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long addFaq(FaqRequest request, Integer operatorId) {
        Faq faq = new Faq()
                .setQuestion(request.getQuestion())
                .setAnswer(request.getAnswer())
                .setCategory(request.getCategory() == null ? "" : request.getCategory())
                .setTags(request.getTags() == null ? "" : request.getTags())
                .setEnabled(request.getEnabled() == null ? 1 : request.getEnabled())
                .setHitCount(0L)
                .setOperatorId(operatorId == null ? 0 : operatorId);
        faqMapper.insert(faq);
        knowledgeAdminClient.syncFaqs(java.util.List.of(faq));
        logChange("FAQ", faq.getId(), "CREATE", "新增 FAQ", faq.getOperatorId());
        return faq.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateFaq(Long id, FaqRequest request, Integer operatorId) {
        Faq faq = faqDetail(id);
        faq.setQuestion(request.getQuestion());
        faq.setAnswer(request.getAnswer());
        if (request.getCategory() != null) faq.setCategory(request.getCategory());
        if (request.getTags() != null) faq.setTags(request.getTags());
        if (request.getEnabled() != null) faq.setEnabled(request.getEnabled());
        faq.setOperatorId(operatorId == null ? 0 : operatorId);
        faqMapper.updateById(faq);
        knowledgeAdminClient.syncFaqs(java.util.List.of(faq));
        logChange("FAQ", id, "UPDATE", "编辑 FAQ", faq.getOperatorId());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteFaq(Long id, Integer operatorId) {
        faqDetail(id);
        faqMapper.deleteById(id);
        knowledgeAdminClient.deleteFaq(id);
        logChange("FAQ", id, "DELETE", "删除 FAQ", operatorId);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void toggleFaq(Long id, Integer operatorId) {
        Faq faq = faqDetail(id);
        int next = Integer.valueOf(1).equals(faq.getEnabled()) ? 0 : 1;
        faq.setEnabled(next);
        faq.setOperatorId(operatorId == null ? 0 : operatorId);
        faqMapper.updateById(faq);
        knowledgeAdminClient.updateFaqEnabled(id, next == 1);
        logChange("FAQ", id, "TOGGLE", next == 1 ? "启用" : "停用", faq.getOperatorId());
    }

    // ─── 检索测试 ───

    @Override
    public Map<String, Object> testRetrieval(String query, Map<String, Object> params, Integer operatorId) {
        JsonNode result = knowledgeAdminClient.retrieve(query, params);
        RetrievalTest record = new RetrievalTest()
                .setQueryText(query)
                .setParams(toJson(params == null ? Map.of() : params))
                .setResults(result.toString())
                .setOperatorId(operatorId == null ? 0 : operatorId);
        retrievalTestMapper.insert(record);
        return Map.of("id", record.getId(), "result", result);
    }

    @Override
    public IPage<RetrievalTest> testHistory(Integer current, Integer size) {
        return retrievalTestMapper.selectPage(new Page<>(current, size),
                new LambdaQueryWrapper<RetrievalTest>().orderByDesc(RetrievalTest::getId));
    }

    // ─── MCP 工具方法 ───

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateIngestStatus(Long docId, String status, Integer chunkCount, String errorMessage) {
        KnowledgeDoc doc = getById(docId);
        if (doc == null) {
            throw new BusinessException(BusinessStatusEnum.NOT_FOUND, "文档不存在");
        }
        doc.setStatus(status);
        if (chunkCount != null) {
            doc.setChunkCount(chunkCount);
        }
        doc.setErrorMessage(errorMessage == null ? "" : errorMessage);
        updateById(doc);
        logChange("DOC", docId, "INGEST", "处理完成: " + status, doc.getOperatorId());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void incrementFaqHit(Long faqId) {
        Faq faq = faqMapper.selectById(faqId);
        if (faq == null) {
            return;
        }
        faq.setHitCount((faq.getHitCount() == null ? 0L : faq.getHitCount()) + 1);
        faqMapper.updateById(faq);
    }

    // ─── 内部方法 ───

    private void logChange(String targetType, Long targetId, String action, String detail, Integer operatorId) {
        changeLogMapper.insert(new KnowledgeChangeLog()
                .setTargetType(targetType)
                .setTargetId(targetId)
                .setAction(action)
                .setDetail(detail)
                .setOperatorId(operatorId == null ? 0 : operatorId)
                .setCreateTime(LocalDateTime.now()));
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            return "{}";
        }
    }

    private String stripSuffix(String name) {
        int dot = name.lastIndexOf(".");
        return dot > 0 ? name.substring(0, dot) : name;
    }
}
