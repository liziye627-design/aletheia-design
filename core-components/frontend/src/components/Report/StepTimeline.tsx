import type { StreamedReasoningStep } from '../../types/runtime'
import { cn } from '../../lib/cn'

interface StepTimelineProps {
  steps: StreamedReasoningStep[]
  activeStepIndex: number
  onStepClick: (index: number) => void
}

const STAGE_NAME_MAP: Record<string, string> = {
  preprocessing: '预处理',
  physical_check: '物理校验',
  logical_check: '逻辑校验',
  source_analysis: '信源分析',
  cross_validation: '交叉验证',
  anomaly_detection: '异常检测',
  evidence_synthesis: '证据综合',
  self_reflection: '自我反思',
}

function displayStage(stage: string) {
  return STAGE_NAME_MAP[stage] || stage
}

export function StepTimeline({ steps, activeStepIndex, onStepClick }: StepTimelineProps) {
  if (steps.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-slate-500">
        等待后端返回推理链...
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="h-1.5 w-full rounded-full bg-slate-800">
        <div
          className="h-full rounded-full bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-500 transition-all duration-300"
          style={{
            width: `${Math.max(10, ((activeStepIndex + 1) / steps.length) * 100)}%`,
          }}
        />
      </div>

      <div className="grid gap-2 md:grid-cols-4 xl:grid-cols-8">
        {steps.map((step, index) => {
          const isActive = activeStepIndex === index
          return (
            <button
              key={`${step.stage}-${index}`}
              onClick={() => onStepClick(index)}
              className={cn(
                'rounded-xl border px-2 py-2 text-left transition',
                'border-slate-700 bg-slate-900 hover:border-slate-500',
                step.status === 'done' && 'border-emerald-500/60 bg-emerald-950/30',
                step.status === 'streaming' && 'border-cyan-400/70 bg-cyan-950/30',
                isActive && 'ring-2 ring-cyan-300/70'
              )}
            >
              <p className="text-[11px] font-semibold text-slate-300">Step {index + 1}</p>
              <p className="mt-1 line-clamp-2 text-xs font-medium text-slate-100">
                {displayStage(step.stage)}
              </p>
              <p className="mt-1 text-[11px] text-slate-500">
                {step.status === 'done'
                  ? '完成'
                  : step.status === 'streaming'
                    ? '流式输出中'
                    : '待执行'}
              </p>
            </button>
          )
        })}
      </div>
    </div>
  )
}
