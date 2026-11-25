package com.qiujie.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.qiujie.dto.FaqRequest;
import com.qiujie.vo.KnowledgeChunkVO;
import com.qiujie.dto.KnowledgeDocUpdateRequest;
import com.qiujie.entity.Faq;
import com.qiujie.entity.KnowledgeChangeLog;
import com.qiujie.entity.KnowledgeDoc;
import com.qiujie.entity.RetrievalTest;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

/**
 * 知识库管理服务。
 *
 * @author qiujie
 */
public interface KnowledgeService {

    /** 上传文档：落盘 + 建记录 + 异步触发处理，返回文档记录 */
    KnowledgeDoc upload(MultipartFile file, String category, String tags, Integer operatorId);

    IPage<KnowledgeDoc> listDocs(Integer current, Integer size, String category, String tags,
                                 String status, Integer enabled);

    KnowledgeDoc docDetail(Long id);

    void updateDoc(Long id, KnowledgeDocUpdateRequest request, Integer operatorId);

    void deleteDoc(Long id, Integer operatorId);

    void toggleDoc(Long id, Integer operatorId);

    void retryDoc(Long id, Integer operatorId);

    void rebuild(Integer operatorId);

    IPage<KnowledgeChangeLog> changeLogs(Integer current, Integer size, String targetType);

    /** 列出文档分块（只取 Qdrant payload）。 */
    List<KnowledgeChunkVO> listChunks(Long docId);

    /** 编辑单块正文：立即重算向量。 */
    void updateChunk(Long docId, Integer chunkIndex, String content, Integer operatorId);

    /** 启停单块。 */
    void setChunkEnabled(Long docId, Integer chunkIndex, boolean enabled, Integer operatorId);

    /** 删除单块，chunkIndex 留空洞。 */
    void deleteChunk(Long docId, Integer chunkIndex, Integer operatorId);

    IPage<Faq> listFaqs(Integer current, Integer size, String category, Integer enabled);

    Faq faqDetail(Long id);

    Long addFaq(FaqRequest request, Integer operatorId);

    void updateFaq(Long id, FaqRequest request, Integer operatorId);

    void deleteFaq(Long id, Integer operatorId);

    void toggleFaq(Long id, Integer operatorId);

    /** 检索测试：调 Python + 落库，返回测试结果（含记录 ID） */
    Map<String, Object> testRetrieval(String query, Map<String, Object> params, Integer operatorId);

    IPage<RetrievalTest> testHistory(Integer current, Integer size);

    /** MCP 工具：回写文档处理状态（Python 处理完调用） */
    void updateIngestStatus(Long docId, String status, Integer chunkCount, String errorMessage);

    /** MCP 工具：FAQ 命中计数 +1 */
    void incrementFaqHit(Long faqId);
}
