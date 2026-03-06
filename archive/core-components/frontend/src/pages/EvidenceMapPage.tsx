import { useState, useEffect, useCallback } from 'react'
import {
  searchEvidence,
  getEvidenceDocument,
  getEvidenceStats,
  findSimilarEvidence,
} from '../api'
import type {
  EvidenceDocument,
  EvidenceSearchResponse,
  EvidenceStatsResponse,
} from '../api'

export default function EvidenceMapPage() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<EvidenceSearchResponse | null>(null)
  const [stats, setStats] = useState<EvidenceStatsResponse | null>(null)
  const [selectedDoc, setSelectedDoc] = useState<EvidenceDocument | null>(null)
  const [activeTab, setActiveTab] = useState<'search' | 'stats' | 'map'>('search')

  // 加载统计信息
  useEffect(() => {
    loadStats()
  }, [])

  const loadStats = async () => {
    try {
      const data = await getEvidenceStats()
      setStats(data)
    } catch (err) {
      console.error('加载统计失败:', err)
    }
  }

  // 搜索证据
  const handleSearch = useCallback(async () => {
    if (!query.trim()) return

    setLoading(true)
    setError(null)

    try {
      const response = await searchEvidence({
        query: query.trim(),
        size: 20,
        highlight: true,
      })
      setResults(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : '搜索失败')
    } finally {
      setLoading(false)
    }
  }, [query])

  // 查看文档详情
  const handleViewDoc = async (docId: string) => {
    try {
      const doc = await getEvidenceDocument(docId)
      setSelectedDoc(doc)
    } catch (err) {
      console.error('获取文档详情失败:', err)
    }
  }

  // 查找相似文档
  const handleFindSimilar = async (docId: string) => {
    setLoading(true)
    try {
      const response = await findSimilarEvidence({ doc_id: docId, k: 10 })
      setResults(response)
      setActiveTab('search')
    } catch (err) {
      setError(err instanceof Error ? err.message : '相似检索失败')
    } finally {
      setLoading(false)
    }
  }

  // 获取来源层级颜色
  const getTierColor = (tier: string) => {
    switch (tier) {
      case 'S': return '#10b981' // green
      case 'A': return '#3b82f6' // blue
      case 'B': return '#f59e0b' // amber
      case 'C': return '#ef4444' // red
      default: return '#6b7280' // gray
    }
  }

  // 获取可信度等级
  const getCredibilityLabel = (score: number) => {
    if (score >= 0.8) return { label: '极高', color: '#10b981' }
    if (score >= 0.6) return { label: '高', color: '#3b82f6' }
    if (score >= 0.4) return { label: '中', color: '#f59e0b' }
    if (score >= 0.2) return { label: '低', color: '#f97316' }
    return { label: '极低', color: '#ef4444' }
  }

  return (
    <>
      <section className="head-row">
        <div>
          <h1>证据库</h1>
          <p>证据搜索、可信度评分与版本追踪</p>
        </div>
        {stats && (
          <div className="stats-summary">
            <span>文档: {stats.total_documents.toLocaleString()}</span>
            <span>版本: {stats.total_versions.toLocaleString()}</span>
            <span>平均评分: {(stats.avg_evidence_score * 100).toFixed(1)}%</span>
          </div>
        )}
      </section>

      {/* 标签页切换 */}
      <div className="tab-bar">
        <button
          className={activeTab === 'search' ? 'active' : ''}
          onClick={() => setActiveTab('search')}
        >
          证据搜索
        </button>
        <button
          className={activeTab === 'stats' ? 'active' : ''}
          onClick={() => setActiveTab('stats')}
        >
          统计分析
        </button>
        <button
          className={activeTab === 'map' ? 'active' : ''}
          onClick={() => setActiveTab('map')}
        >
          证据地图
        </button>
      </div>

      {/* 搜索面板 */}
      {activeTab === 'search' && (
        <section className="panel">
          <div className="search-box">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="输入关键词搜索证据..."
              className="search-input"
            />
            <button onClick={handleSearch} disabled={loading} className="search-btn">
              {loading ? '搜索中...' : '搜索'}
            </button>
          </div>

          {error && <div className="error-msg">{error}</div>}

          {/* 搜索结果 */}
          {results && (
            <div className="results-section">
              <div className="results-header">
                <span>找到 {results.total} 条证据</span>
                <span>耗时 {results.took_ms}ms</span>
              </div>

              <div className="results-list">
                {results.hits.map((doc) => {
                  const credibility = getCredibilityLabel(doc.evidence_score)
                  return (
                    <div
                      key={doc.doc_id}
                      className="evidence-card"
                      onClick={() => handleViewDoc(doc.doc_id)}
                    >
                      <div className="card-header">
                        <span className="platform-tag">{doc.platform}</span>
                        <span
                          className="tier-tag"
                          style={{ backgroundColor: getTierColor(doc.source_tier) }}
                        >
                          {doc.source_tier}级来源
                        </span>
                        <span
                          className="credibility-tag"
                          style={{ color: credibility.color }}
                        >
                          可信度: {credibility.label} ({(doc.evidence_score * 100).toFixed(0)}%)
                        </span>
                      </div>

                      <h3 className="card-title">{doc.title}</h3>

                      <p className="card-snippet">
                        {doc._highlight?.content_text?.[0] ||
                          (doc.content_text?.slice(0, 200) + '...')}
                      </p>

                      <div className="card-footer">
                        <span className="source-domain">{doc.source_domain}</span>
                        <span className="crawl-time">
                          {new Date(doc.crawl_time).toLocaleDateString()}
                        </span>
                      </div>

                      <div className="card-actions">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleFindSimilar(doc.doc_id)
                          }}
                          className="similar-btn"
                        >
                          查找相似
                        </button>
                        <a
                          href={doc.canonical_url || doc.original_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="view-url"
                        >
                          查看原文
                        </a>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </section>
      )}

      {/* 统计面板 */}
      {activeTab === 'stats' && stats && (
        <section className="panel stats-panel">
          <h2>证据库统计</h2>

          <div className="stats-grid">
            <div className="stat-card">
              <h3>总文档数</h3>
              <div className="stat-value">{stats.total_documents.toLocaleString()}</div>
            </div>
            <div className="stat-card">
              <h3>总版本数</h3>
              <div className="stat-value">{stats.total_versions.toLocaleString()}</div>
            </div>
            <div className="stat-card">
              <h3>搜索命中</h3>
              <div className="stat-value">{stats.total_search_hits.toLocaleString()}</div>
            </div>
            <div className="stat-card">
              <h3>平均评分</h3>
              <div className="stat-value">{(stats.avg_evidence_score * 100).toFixed(1)}%</div>
            </div>
          </div>

          <div className="stats-section">
            <h3>按来源层级分布</h3>
            <div className="tier-distribution">
              {Object.entries(stats.by_source_tier).map(([tier, count]) => (
                <div key={tier} className="tier-bar">
                  <span className="tier-label">{tier}级</span>
                  <div className="bar-container">
                    <div
                      className="bar-fill"
                      style={{
                        width: `${(count / stats.total_documents * 100) || 0}%`,
                        backgroundColor: getTierColor(tier),
                      }}
                    />
                  </div>
                  <span className="tier-count">{count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="stats-section">
            <h3>按平台分布</h3>
            <div className="platform-list">
              {Object.entries(stats.by_platform)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 10)
                .map(([platform, count]) => (
                  <div key={platform} className="platform-item">
                    <span className="platform-name">{platform}</span>
                    <span className="platform-count">{count.toLocaleString()}</span>
                  </div>
                ))}
            </div>
          </div>

          <div className="stats-section">
            <h3>提取方法分布</h3>
            <div className="method-list">
              {Object.entries(stats.by_extraction_method).map(([method, count]) => (
                <div key={method} className="method-item">
                  <span className="method-name">{method}</span>
                  <span className="method-count">{count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="stats-footer">
            <span>索引大小: {(stats.index_size_mb).toFixed(2)} MB</span>
            <span>最后更新: {new Date(stats.last_updated).toLocaleString()}</span>
          </div>
        </section>
      )}

      {/* 证据地图 */}
      {activeTab === 'map' && (
        <section className="panel evidence-layout">
          <div className="map-canvas">
            <div className="map-line" />
            {results?.hits.slice(0, 5).map((doc, idx) => {
              const nodeType = doc.evidence_score >= 0.6 ? 'ok' :
                              doc.evidence_score >= 0.3 ? 'neutral' : 'risk'
              return (
                <div
                  key={doc.doc_id}
                  className={`map-node ${nodeType}`}
                  style={{
                    left: `${80 + idx * 170}px`,
                    top: `${idx % 2 === 0 ? 70 : 160}px`,
                  }}
                  onClick={() => handleViewDoc(doc.doc_id)}
                >
                  <strong>{doc.platform.slice(0, 2).toUpperCase()}</strong>
                  <span>{doc.title.slice(0, 15)}...</span>
                </div>
              )
            })}
          </div>

          <div className="insight-card">
            <h3>节点说明</h3>
            <div className="tag ok">绿色 - 高可信度证据 (≥60%)</div>
            <div className="tag neutral">灰色 - 中等可信度 (30-60%)</div>
            <div className="tag bad">红色 - 低可信度证据 (&lt;30%)</div>
            <div className="tag action">点击节点查看详情</div>
          </div>
        </section>
      )}

      {/* 文档详情弹窗 */}
      {selectedDoc && (
        <div className="modal-overlay" onClick={() => setSelectedDoc(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>证据详情</h2>
              <button onClick={() => setSelectedDoc(null)}>×</button>
            </div>

            <div className="modal-body">
              <div className="detail-row">
                <label>标题:</label>
                <span>{selectedDoc.title}</span>
              </div>

              <div className="detail-row">
                <label>平台:</label>
                <span className="platform-tag">{selectedDoc.platform}</span>
              </div>

              <div className="detail-row">
                <label>来源层级:</label>
                <span style={{ color: getTierColor(selectedDoc.source_tier) }}>
                  {selectedDoc.source_tier}级
                </span>
              </div>

              <div className="detail-row">
                <label>可信度:</label>
                <span style={{ color: getCredibilityLabel(selectedDoc.evidence_score).color }}>
                  {(selectedDoc.evidence_score * 100).toFixed(1)}%
                </span>
              </div>

              <div className="detail-row">
                <label>提取方法:</label>
                <span>{selectedDoc.extraction_method}</span>
                <span className="confidence">
                  (置信度: {(selectedDoc.extraction_confidence * 100).toFixed(0)}%)
                </span>
              </div>

              <div className="detail-row">
                <label>原文链接:</label>
                <a
                  href={selectedDoc.canonical_url || selectedDoc.original_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {selectedDoc.original_url}
                </a>
              </div>

              <div className="detail-content">
                <label>内容摘要:</label>
                <p>{selectedDoc.content_text?.slice(0, 500)}...</p>
              </div>
            </div>

            <div className="modal-footer">
              <button onClick={() => handleFindSimilar(selectedDoc.doc_id)}>
                查找相似证据
              </button>
              <button onClick={() => setSelectedDoc(null)}>关闭</button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .head-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
        }
        .stats-summary {
          display: flex;
          gap: 1.5rem;
          font-size: 0.9rem;
          color: #666;
        }
        .tab-bar {
          display: flex;
          gap: 0.5rem;
          margin-bottom: 1rem;
        }
        .tab-bar button {
          padding: 0.5rem 1rem;
          border: 1px solid #ddd;
          background: #fff;
          cursor: pointer;
          border-radius: 4px;
        }
        .tab-bar button.active {
          background: #3b82f6;
          color: white;
          border-color: #3b82f6;
        }
        .search-box {
          display: flex;
          gap: 0.5rem;
          margin-bottom: 1rem;
        }
        .search-input {
          flex: 1;
          padding: 0.75rem;
          border: 1px solid #ddd;
          border-radius: 4px;
          font-size: 1rem;
        }
        .search-btn {
          padding: 0.75rem 1.5rem;
          background: #3b82f6;
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
        }
        .search-btn:disabled {
          background: #93c5fd;
        }
        .error-msg {
          color: #ef4444;
          padding: 0.5rem;
          background: #fef2f2;
          border-radius: 4px;
          margin-bottom: 1rem;
        }
        .results-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 1rem;
          color: #666;
          font-size: 0.9rem;
        }
        .evidence-card {
          border: 1px solid #e5e7eb;
          border-radius: 8px;
          padding: 1rem;
          margin-bottom: 0.75rem;
          cursor: pointer;
          transition: box-shadow 0.2s;
        }
        .evidence-card:hover {
          box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .card-header {
          display: flex;
          gap: 0.5rem;
          margin-bottom: 0.5rem;
          flex-wrap: wrap;
        }
        .platform-tag, .tier-tag {
          padding: 0.25rem 0.5rem;
          border-radius: 4px;
          font-size: 0.75rem;
        }
        .platform-tag {
          background: #f3f4f6;
        }
        .tier-tag {
          color: white;
        }
        .credibility-tag {
          font-size: 0.85rem;
          font-weight: 500;
        }
        .card-title {
          margin: 0.5rem 0;
          font-size: 1rem;
        }
        .card-snippet {
          color: #666;
          font-size: 0.9rem;
          margin: 0.5rem 0;
        }
        .card-footer {
          display: flex;
          justify-content: space-between;
          color: #999;
          font-size: 0.8rem;
          margin-top: 0.5rem;
        }
        .card-actions {
          display: flex;
          gap: 0.5rem;
          margin-top: 0.75rem;
        }
        .similar-btn {
          padding: 0.25rem 0.75rem;
          background: #f3f4f6;
          border: 1px solid #ddd;
          border-radius: 4px;
          cursor: pointer;
          font-size: 0.85rem;
        }
        .view-url {
          padding: 0.25rem 0.75rem;
          background: #3b82f6;
          color: white;
          border-radius: 4px;
          text-decoration: none;
          font-size: 0.85rem;
        }
        .stats-panel {
          padding: 1.5rem;
        }
        .stats-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 1rem;
          margin-bottom: 1.5rem;
        }
        .stat-card {
          background: #f9fafb;
          padding: 1rem;
          border-radius: 8px;
          text-align: center;
        }
        .stat-card h3 {
          margin: 0 0 0.5rem 0;
          font-size: 0.9rem;
          color: #666;
        }
        .stat-value {
          font-size: 1.5rem;
          font-weight: bold;
        }
        .stats-section {
          margin-bottom: 1.5rem;
        }
        .stats-section h3 {
          margin-bottom: 0.75rem;
        }
        .tier-bar {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          margin-bottom: 0.5rem;
        }
        .tier-label {
          width: 40px;
        }
        .bar-container {
          flex: 1;
          height: 20px;
          background: #f3f4f6;
          border-radius: 4px;
          overflow: hidden;
        }
        .bar-fill {
          height: 100%;
          transition: width 0.3s;
        }
        .tier-count {
          width: 80px;
          text-align: right;
        }
        .platform-list, .method-list {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 0.5rem;
        }
        .platform-item, .method-item {
          display: flex;
          justify-content: space-between;
          padding: 0.5rem;
          background: #f9fafb;
          border-radius: 4px;
        }
        .stats-footer {
          display: flex;
          justify-content: space-between;
          color: #999;
          font-size: 0.85rem;
          padding-top: 1rem;
          border-top: 1px solid #eee;
        }
        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0,0,0,0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }
        .modal-content {
          background: white;
          border-radius: 8px;
          width: 600px;
          max-height: 80vh;
          overflow-y: auto;
        }
        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 1rem;
          border-bottom: 1px solid #eee;
        }
        .modal-header button {
          background: none;
          border: none;
          font-size: 1.5rem;
          cursor: pointer;
        }
        .modal-body {
          padding: 1rem;
        }
        .detail-row {
          display: flex;
          gap: 0.5rem;
          margin-bottom: 0.75rem;
        }
        .detail-row label {
          font-weight: 500;
          min-width: 100px;
        }
        .detail-content {
          margin-top: 1rem;
        }
        .detail-content label {
          display: block;
          font-weight: 500;
          margin-bottom: 0.5rem;
        }
        .detail-content p {
          background: #f9fafb;
          padding: 0.75rem;
          border-radius: 4px;
          font-size: 0.9rem;
          line-height: 1.6;
        }
        .modal-footer {
          display: flex;
          justify-content: flex-end;
          gap: 0.5rem;
          padding: 1rem;
          border-top: 1px solid #eee;
        }
        .modal-footer button {
          padding: 0.5rem 1rem;
          border-radius: 4px;
          cursor: pointer;
        }
        .map-canvas {
          position: relative;
          height: 300px;
          background: #f9fafb;
          border-radius: 8px;
          margin-bottom: 1rem;
        }
        .map-node {
          position: absolute;
          padding: 0.75rem;
          border-radius: 8px;
          cursor: pointer;
          min-width: 100px;
          text-align: center;
        }
        .map-node.ok { background: #d1fae5; border: 2px solid #10b981; }
        .map-node.risk { background: #fee2e2; border: 2px solid #ef4444; }
        .map-node.neutral { background: #f3f4f6; border: 2px solid #6b7280; }
        .map-node strong { display: block; font-size: 1.2rem; }
        .map-node span { font-size: 0.75rem; color: #666; }
        .insight-card {
          background: #f9fafb;
          padding: 1rem;
          border-radius: 8px;
        }
        .insight-card h3 { margin: 0 0 0.75rem 0; }
        .tag {
          padding: 0.25rem 0.5rem;
          border-radius: 4px;
          margin-bottom: 0.5rem;
          display: block;
          font-size: 0.85rem;
        }
        .tag.ok { background: #d1fae5; }
        .tag.bad { background: #fee2e2; }
        .tag.neutral { background: #f3f4f6; }
        .tag.action { background: #dbeafe; }
      `}</style>
    </>
  )
}