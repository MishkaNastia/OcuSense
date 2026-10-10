import { MeasurementPanel } from "@/components/measure/MeasurementPanel";
import { OpennessGraph } from "@/components/measure/OpennessGraph";
import { SampleSession } from "@/lib/demo/sampleSession";

/**
 * Static product preview computed from the synthetic sample session with the
 * real measurement engine (runs at build time; no camera, no animation).
 */
export function SamplePreview() {
  const sample = new SampleSession(11);
  sample.advance(70);
  const snapshot = sample.session.snapshot(sample.t);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <OpennessGraph samples={sample.session.graphSamples()} now={sample.t}
        label="Sample data: simulated personal eye openness over the last 10 seconds, with counted blinks marked" />
      <MeasurementPanel snapshot={snapshot} opennessRaw={sample.latestOpenness} source="sample" />
    </div>
  );
}
