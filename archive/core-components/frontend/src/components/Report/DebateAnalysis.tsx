import { useState, useEffect } from 'react'
import { Badge, Card } from '../common'

interface DebateArgument {
  claim: string
  evidence_ids?: string[]
  reasoning: string
  strength?: number
  weakness_type?: string
}

interface DebateAnalysisData {
  claim: string
  keyword: string
  timestamp: string
  debate_process: {
    proponent: {
      stance: string
      main_arguments: DebateArgument[]
      confidence?: number
      key_sources?: string[]
    }
    opponent: {
      stance: string
      main_arguments: DebateArgument[]
      risk_level?: number
      critical_issues?: string[]
    }
    judge: {
      final_verdict: string
      credibility_score: number
      reasoning_summary: string
      key_findings: Array<{
        finding: string
        evidence_support: string[]
        confidence: number
      }>
      recommendation?: string
    }
  }
  final_conclusion: {
    verdict: string
    credibility_score: number
    reasoning_summary: string
    key_findings: any[]
    recommendation: string
  }
  evidence_used: number
  unresolved_questions: string[]
}

interface DebateAnalysisProps {
  debate: DebateAnalysisData | null
}

// 打字机效果Hook
function useTypewriter(text: string, speed: number = 30, startTyping: boolean = true) {
  const [displayText, setDisplayText] = useState('')
  const [isComplete, setIsComplete] = useState(false)
  
  useEffect(() => {
    if (!startTyping || !text) {
      setDisplayText(text || '')
      setIsComplete(true)
      return
    }
    
    let index = 0
    setDisplayText('')
    setIsComplete(false)
    
    const timer = setInterval(() => {
      if (index < text.length) {
        setDisplayText(text.slice(0, index + 1))
        index++
      } else {
        setIsComplete(true)
        clearInterval(timer)
      }
    }, speed)
    
    return () => clearInterval(timer)
  }, [text, speed, startTyping])
  
  return { displayText, isComplete }
}

// 动画卡片组件
function AnimatedCard({ 
  children, 
  delay = 0, 
  className = '',
  borderColor = 'border-slate-500/30',
  bgColor = 'bg-slate-500/10'
}: { 
  children: React.ReactNode
  delay?: number
  className?: string
  borderColor?: string
  bgColor?: string
}) {
  const [isVisible, setIsVisible] = useState(false)
  
  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), delay)
    return () => clearTimeout(timer)
  }, [delay])
  
  return (
    <div 
      className={`
        rounded-xl border ${borderColor} ${bgColor} p-3
        transition-all duration-700 ease-out
        ${isVisible 
          ? 'opacity-100 translate-y-0 scale-100' 
          : 'opacity-0 translate-y-4 scale-95'
        }
        ${className}
      `}
    >
      {children}
    </div>
  )
}

// 打字机文本组件
function TypewriterText({ 
  text, 
  speed = 25, 
  delay = 0,
  className = ''
}: { 
  text: string
  speed?: number
  delay?: number
  className?: string
}) {
  const [startTyping, setStartTyping] = useState(false)
  const { displayText, isComplete } = useTypewriter(text, speed, startTyping)
  
  useEffect(() => {
    const timer = setTimeout(() => setStartTyping(true), delay)
    return () => clearTimeout(timer)
  }, [delay])
  
  return (
    <span className={className}>
      {displayText}
      {!isComplete && <span className="animate-pulse">▌</span>}
    </span>
  )
}

// 单个论点组件
function ArgumentItem({ 
  arg, 
  delay,
  isProponent = true
}: { 
  arg: DebateArgument
  delay: number
  isProponent?: boolean
}) {
  const [showReasoning, setShowReasoning] = useState(false)
  const claimColor = isProponent ? 'text-emerald-200' : 'text-red-200'
  const reasoningColor = isProponent ? 'text-emerald-400/80' : 'text-red-400/80'
  
  useEffect(() => {
    const timer = setTimeout(() => setShowReasoning(true), delay + 500)
    return () => clearTimeout(timer)
  }, [delay])
  
  return (
    <div className="text-xs space-y-1">
      <p className={`font-medium ${claimColor} transition-all duration-300`}>
        {arg.claim}
      </p>
      {showReasoning && (
        <p className={`${reasoningColor} animate-fade-in`}>
          → {arg.reasoning}
        </p>
      )}
    </div>
  )
}

export function DebateAnalysis({ debate }: DebateAnalysisProps) {
  const [phase, setPhase] = useState(0) // 0: 准备, 1: 正方, 2: 反方, 3: 裁判, 4: 完成
  
  useEffect(() => {
    if (!debate) return
    
    const timers = [
      setTimeout(() => setPhase(1), 300),   // 正方开始
      setTimeout(() => setPhase(2), 2000),  // 反方开始
      setTimeout(() => setPhase(3), 4000),  // 裁判开始
      setTimeout(() => setPhase(4), 6000),  // 完成
    ]
    
    return () => timers.forEach(clearTimeout)
  }, [debate])
  
  if (!debate) return null
  
  const { debate_process, final_conclusion, unresolved_questions } = debate
  const proponent = debate_process?.proponent
  const opponent = debate_process?.opponent
  
  const verdictVariant = 
    final_conclusion?.verdict === "SUPPORTED" ? "success" :
    final_conclusion?.verdict === "REFUTED" ? "danger" : "warning"
  
  return (
    <Card className="border-purple-500/30 bg-purple-500/5 overflow-hidden">
      {/* 标题 */}
      <div className="flex items-center gap-2">
        <h3 className="text-lg font-bold text-purple-200">🎭 辩论式推理分析</h3>
        {phase < 4 && (
          <span className="text-xs text-purple-400 animate-pulse">
            {phase === 1 && '正方论证中...'}
            {phase === 2 && '反方质疑中...'}
            {phase === 3 && '综合裁决中...'}
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-slate-400">基于证据的多角度论证过程（动态生成）</p>
      
      {/* 进度条 */}
      <div className="mt-3 h-1 bg-slate-700 rounded-full overflow-hidden">
        <div 
          className="h-full bg-gradient-to-r from-emerald-500 via-red-500 to-cyan-500 transition-all duration-500 ease-out"
          style={{ width: `${(phase / 4) * 100}%` }}
        />
      </div>
      
      <div className="mt-4 space-y-3">
        {/* 正方论证 */}
        {phase >= 1 && (
          <AnimatedCard 
            delay={0} 
            borderColor="border-emerald-500/30" 
            bgColor="bg-emerald-500/10"
          >
            <h4 className="text-sm font-bold text-emerald-300 flex items-center gap-2">
              <span className="text-lg">⚖️</span>
              <TypewriterText text="正方论证" speed={100} delay={0} />
            </h4>
            <div className="mt-2 space-y-2">
              {proponent?.main_arguments?.map((arg, idx) => (
                <ArgumentItem 
                  key={idx} 
                  arg={arg} 
                  delay={idx * 400}
                  isProponent={true}
                />
              ))}
            </div>
            {proponent?.confidence !== undefined && phase >= 2 && (
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-emerald-500 transition-all duration-1000 ease-out"
                    style={{ width: `${proponent.confidence * 100}%` }}
                  />
                </div>
                <span className="text-xs text-emerald-300">
                  {Math.round(proponent.confidence * 100)}%
                </span>
              </div>
            )}
          </AnimatedCard>
        )}
        
        {/* 反方质疑 */}
        {phase >= 2 && (
          <AnimatedCard 
            delay={0} 
            borderColor="border-red-500/30" 
            bgColor="bg-red-500/10"
          >
            <h4 className="text-sm font-bold text-red-300 flex items-center gap-2">
              <span className="text-lg">🔍</span>
              <TypewriterText text="反方质疑" speed={100} delay={0} />
            </h4>
            <div className="mt-2 space-y-2">
              {opponent?.main_arguments?.map((arg, idx) => (
                <ArgumentItem 
                  key={idx} 
                  arg={arg} 
                  delay={idx * 400}
                  isProponent={false}
                />
              ))}
            </div>
            {(opponent?.critical_issues?.length || 0) > 0 && phase >= 3 && (
              <div className="mt-2 animate-fade-in">
                <p className="text-xs font-medium text-red-300">⚠️ 关键问题:</p>
                <ul className="mt-1 list-inside list-disc text-xs text-red-400/80">
                  {opponent?.critical_issues?.map((issue, idx) => (
                    <li key={idx}>{issue}</li>
                  ))}
                </ul>
              </div>
            )}
          </AnimatedCard>
        )}
        
        {/* 综合裁决 */}
        {phase >= 3 && (
          <AnimatedCard 
            delay={0} 
            borderColor="border-cyan-500/30" 
            bgColor="bg-cyan-500/10"
          >
            <h4 className="text-sm font-bold text-cyan-300 flex items-center gap-2">
              <span className="text-lg">🎯</span>
              <TypewriterText text="综合裁决" speed={100} delay={0} />
            </h4>
            <div className="mt-2 flex items-center gap-2">
              <Badge variant={verdictVariant}>
                {final_conclusion?.verdict || "UNCERTAIN"}
              </Badge>
              <span className="text-xs text-slate-300">
                可信度: {Math.round((final_conclusion?.credibility_score || 0.5) * 100)}%
              </span>
            </div>
            <div className="mt-2">
              <TypewriterText 
                text={final_conclusion?.reasoning_summary || ''} 
                speed={15} 
                delay={500}
                className="text-xs text-slate-200"
              />
            </div>
            {final_conclusion?.recommendation && phase >= 4 && (
              <p className="mt-2 text-xs text-cyan-300 animate-fade-in">
                💡 建议: {final_conclusion.recommendation}
              </p>
            )}
          </AnimatedCard>
        )}
        
        {/* 未解决问题 */}
        {phase >= 4 && unresolved_questions?.length > 0 && (
          <AnimatedCard 
            delay={0} 
            borderColor="border-amber-500/30" 
            bgColor="bg-amber-500/10"
          >
            <h4 className="text-sm font-bold text-amber-300">❓ 未解决问题</h4>
            <ul className="mt-2 list-inside list-disc text-xs text-slate-300">
              {unresolved_questions.map((q, idx) => (
                <li key={idx}>{q}</li>
              ))}
            </ul>
          </AnimatedCard>
        )}
      </div>
      
      {/* 自定义动画样式 */}
      <style>{`
        @keyframes fade-in {
          from { opacity: 0; transform: translateY(-5px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in {
          animation: fade-in 0.3s ease-out forwards;
        }
      `}</style>
    </Card>
  )
}
