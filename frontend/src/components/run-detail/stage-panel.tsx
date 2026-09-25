import { PendingPanel, SkippedPanel } from "@/components/run-detail/panel-states"
import { Ab1ExtractionPanel } from "@/components/run-detail/panels/ab1-extraction-panel"
import { BlastPanel } from "@/components/run-detail/panels/blast-panel"
import { ConsensusPanel } from "@/components/run-detail/panels/consensus-panel"
import { FastaPanel } from "@/components/run-detail/panels/fasta-panel"
import { FormatCheckPanel } from "@/components/run-detail/panels/format-check-panel"
import { IdentificationPanel } from "@/components/run-detail/panels/identification-panel"
import { ImportPanel } from "@/components/run-detail/panels/import-panel"
import { OrientationPanel } from "@/components/run-detail/panels/orientation-panel"
import { ReportPanel } from "@/components/run-detail/panels/report-panel"
import { SanityCheckPanel } from "@/components/run-detail/panels/sanity-check-panel"
import { TrimPanel } from "@/components/run-detail/panels/trim-panel"
import { UsabilityCheckPanel } from "@/components/run-detail/panels/usability-check-panel"
import { Skeleton } from "@/components/ui/skeleton"
import { describeSingleReadReason } from "@/lib/single-read-reason"
import type {
  Ab1ExtractionOutput,
  BlastOutput,
  ConsensusOutput,
  ErrorOutput,
  FastaOutput,
  FormatCheckOutput,
  IdentificationOutput,
  ImportOutput,
  OrientationOutput,
  SanityCheckMetadata,
  SanityCheckOutput,
  Stage,
  StageType,
  TrimOutput,
  UsabilityCheckOutput,
} from "@/types/api"

interface StagePanelProps {
  readonly stageType: StageType
  readonly stage: Stage | undefined
  readonly isLoading: boolean
  readonly hasRun: boolean
  readonly runId: string
  readonly sampleId: string
  readonly sanityCheckStage: Stage | undefined
  readonly orientationStage: Stage | undefined
}

export function StagePanel({
  stageType,
  stage,
  isLoading,
  hasRun,
  runId,
  sampleId,
  sanityCheckStage,
  orientationStage,
}: StagePanelProps) {
  if (!hasRun) return <PendingPanel />
  if (isLoading || !stage) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  const singleReadReason = describeSingleReadReason(
    (sanityCheckStage?.stage_metadata as SanityCheckMetadata | null)?.single_read_reason
  )
  const orientationOutput = orientationStage?.output as OrientationOutput | null | undefined

  switch (stageType) {
    case "import":
      return <ImportPanel output={stage.output as ImportOutput} />
    case "format_check":
      return <FormatCheckPanel output={stage.output as FormatCheckOutput} />
    case "ab1_extraction":
      return <Ab1ExtractionPanel output={stage.output as Ab1ExtractionOutput} />
    case "sanity_check":
      return (
        <SanityCheckPanel
          output={stage.output as SanityCheckOutput}
          metadata={stage.stage_metadata as SanityCheckMetadata | null}
        />
      )
    case "trim":
      return <TrimPanel output={stage.output as TrimOutput} />
    case "orientation":
      if (stage.status === "skipped") return <SkippedPanel reason={singleReadReason ?? "Not applicable to this run."} />
      return <OrientationPanel output={stage.output as OrientationOutput} singleReadReason={singleReadReason} />
    case "consensus":
      if (stage.status === "skipped") {
        return (
          <ConsensusPanel
            output={null}
            orientationFoundNoOverlap={orientationOutput?.orientation === "no_overlap_found"}
            singleReadReason={singleReadReason}
          />
        )
      }
      return (
        <ConsensusPanel
          output={stage.output as ConsensusOutput | ErrorOutput}
          orientationFoundNoOverlap={false}
        />
      )
    case "usability_check":
      return <UsabilityCheckPanel output={stage.output as UsabilityCheckOutput} />
    case "fasta":
      return <FastaPanel output={stage.output as FastaOutput | ErrorOutput} />
    case "blast":
      return <BlastPanel output={stage.output as BlastOutput} />
    case "identification":
      return <IdentificationPanel output={stage.output as IdentificationOutput} />
    case "report":
      return <ReportPanel runId={runId} sampleId={sampleId} />
    default:
      return null
  }
}
