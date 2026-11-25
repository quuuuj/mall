package com.qiujie.client;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.qiujie.vo.KnowledgeChunkVO;
import com.qiujie.entity.Faq;
import com.qiujie.entity.KnowledgeDoc;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.scheduler.Schedulers;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

/**
 * 调用 mall-customer 知识库管理接口的客户端。
 * <p>
 * 复用 customerWebClient（已带共享密钥）。ingest 是长任务（OCR 可能几分钟），
 * 发出即返回，Python 处理完经 MCP 回写状态；其余接口同步等待结果。
 *
 * @author qiujie
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class KnowledgeAdminClient {

    private final WebClient customerWebClient;
    private final ObjectMapper objectMapper;

    /** 触发单文档处理，不等待结果。 */
    public void ingest(KnowledgeDoc doc, Path filePath) {
        Map<String, Object> body = Map.of(
                "docId", doc.getId(),
                "filePath", filePath.toString(),
                "title", doc.getTitle() == null ? "" : doc.getTitle(),
                "chunkSize", doc.getChunkSize(),
                "chunkOverlap", doc.getChunkOverlap(),
                "cleanRules", doc.getCleanRules() == null ? "{}" : doc.getCleanRules()
        );
        customerWebClient.post()
                .uri("/api/admin/ingest")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .toBodilessEntity()
                .subscribeOn(Schedulers.boundedElastic())
                .subscribe(
                        r -> log.info("已触发文档 {} 处理", doc.getId()),
                        e -> log.error("触发文档 {} 处理失败", doc.getId(), e)
                );
    }

    /** 全量重建文档向量。 */
    public void rebuild() {
        customerWebClient.post()
                .uri("/api/admin/rebuild")
                .retrieve()
                .toBodilessEntity()
                .block();
    }

    /** 删除文档向量。 */
    public void deleteDoc(Long docId) {
        customerWebClient.delete()
                .uri("/api/admin/doc/{docId}", docId)
                .retrieve()
                .toBodilessEntity()
                .block();
    }

    /** 删除 FAQ 向量。 */
    public void deleteFaq(Long faqId) {
        customerWebClient.delete()
                .uri("/api/admin/faq/{faqId}", faqId)
                .retrieve()
                .toBodilessEntity()
                .block();
    }

    /** 更新文档启用标记（向量 payload）。 */
    public void updateDocEnabled(Long docId, boolean enabled) {
        customerWebClient.put()
                .uri("/api/admin/doc/{docId}/enabled", docId)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("enabled", enabled))
                .retrieve()
                .toBodilessEntity()
                .block();
    }

    /** 更新 FAQ 启用标记（向量 payload）。 */
    public void updateFaqEnabled(Long faqId, boolean enabled) {
        customerWebClient.put()
                .uri("/api/admin/faq/{faqId}/enabled", faqId)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("enabled", enabled))
                .retrieve()
                .toBodilessEntity()
                .block();
    }

    /** 全量同步 FAQ 向量。 */
    public void syncFaqs(List<Faq> faqs) {
        List<Map<String, Object>> payload = faqs.stream().map(f -> Map.<String, Object>of(
                "faqId", f.getId(),
                "question", f.getQuestion(),
                "answer", f.getAnswer(),
                "category", f.getCategory() == null ? "" : f.getCategory(),
                "tags", f.getTags() == null ? "" : f.getTags(),
                "enabled", Integer.valueOf(1).equals(f.getEnabled())
        )).toList();
        customerWebClient.post()
                .uri("/api/admin/faq/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("faqs", payload))
                .retrieve()
                .toBodilessEntity()
                .block();
    }

    /** 检索测试：返回 Python 的完整结果 JSON。 */
    public JsonNode retrieve(String query, Map<String, Object> params) {
        String json = customerWebClient.post()
                .uri("/api/admin/retrieve")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("query", query, "params", params == null ? Map.of() : params))
                .retrieve()
                .bodyToMono(String.class)
                .block();
        try {
            return objectMapper.readTree(json == null ? "{}" : json);
        } catch (Exception e) {
            throw new IllegalStateException("检索结果解析失败", e);
        }
    }

    // ─── 单块编辑 ───

    /** 列出文档分块。 */
    public List<KnowledgeChunkVO> listChunks(Long docId) {
        String json = customerWebClient.get()
                .uri("/api/admin/doc/{docId}/chunks", docId)
                .retrieve()
                .bodyToMono(String.class)
                .block();
        try {
            JsonNode node = objectMapper.readTree(json == null ? "{}" : json);
            JsonNode chunks = node.path("chunks");
            if (!chunks.isArray()) {
                return List.of();
            }
            return objectMapper.convertValue(chunks, new TypeReference<List<KnowledgeChunkVO>>() {});
        } catch (Exception e) {
            throw new IllegalStateException("分块列表解析失败", e);
        }
    }

    /** 编辑单块正文：立即重算向量。 */
    public void updateChunkContent(Long docId, Integer chunkIndex, String content) {
        customerWebClient.put()
                .uri("/api/admin/doc/{docId}/chunks/{chunkIndex}", docId, chunkIndex)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("content", content))
                .retrieve()
                .toBodilessEntity()
                .block();
    }

    /** 启停单块。 */
    public void updateChunkEnabled(Long docId, Integer chunkIndex, boolean enabled) {
        customerWebClient.put()
                .uri("/api/admin/doc/{docId}/chunks/{chunkIndex}/enabled", docId, chunkIndex)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("enabled", enabled))
                .retrieve()
                .toBodilessEntity()
                .block();
    }

    /** 删除单块（chunk_index 留空洞）。 */
    public void deleteChunk(Long docId, Integer chunkIndex) {
        customerWebClient.delete()
                .uri("/api/admin/doc/{docId}/chunks/{chunkIndex}", docId, chunkIndex)
                .retrieve()
                .toBodilessEntity()
                .block();
    }
}
