import type { Metadata } from "next";
import Link from "next/link";

import { SampleDemo } from "@/components/demo/SampleDemo";

export const metadata: Metadata = { title: "Sample session demo" };

export default function SampleDemoPage() {
  return (
    <div className="container page" style={{ gap: 28 }}>
      <header className="prose">
        <p className="eyebrow"><Link href="/demo">Demo</Link> · Option A</p>
        <h1>Explore a sample session</h1>
        <p className="lead">
          No camera needed. A simulated person studies while the real OcuSense measurement rules run on their
          synthetic eye data. Trigger prompts, take a break, and explore their patterns.
        </p>
      </header>
      <SampleDemo />
    </div>
  );
}
