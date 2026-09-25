// Backend sorts species_breakdown (count desc, species asc) but never caps
// it -- DESIGN.md's "3 direct-labeled categories + Other" donut rule (which
// mirrors the dataviz skill's all-pairs categorical cap) is a frontend job.
export interface SpeciesSlice {
  species: string
  count: number
  percentage: number
  isOther: boolean
}

export function buildSpeciesBreakdown(
  entries: { species: string; count: number }[]
): SpeciesSlice[] {
  const total = entries.reduce((sum, e) => sum + e.count, 0)
  if (total === 0) return []

  const top = entries.slice(0, 3)
  const otherCount = entries.slice(3).reduce((sum, e) => sum + e.count, 0)

  const slices: SpeciesSlice[] = top.map((e) => ({
    species: e.species,
    count: e.count,
    percentage: (e.count / total) * 100,
    isOther: false,
  }))

  if (otherCount > 0) {
    slices.push({
      species: "Other",
      count: otherCount,
      percentage: (otherCount / total) * 100,
      isOther: true,
    })
  }

  return slices
}
