// The universal Sanger-chromatogram color convention (Sequencher, 4Peaks,
// SnapGene, the sequencer manufacturers' own software) -- every
// bioinformatician reading this screen already knows these four colors by
// muscle memory. This overrides the app's own categorical brand palette on
// purpose: for a domain-standard signal plot, matching what every other
// tool shows is more legible than brand consistency would be.
export const BASE_COLORS: Record<string, string> = {
  A: "#16a34a",
  C: "#2563eb",
  G: "#1f2937",
  T: "#dc2626",
}

export function colorForBase(base: string) {
  return BASE_COLORS[base] ?? "var(--muted-foreground)"
}
