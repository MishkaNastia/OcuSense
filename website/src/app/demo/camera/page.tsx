import type { Metadata } from "next";
import Link from "next/link";

import { CameraDemo } from "@/components/demo/CameraDemo";

export const metadata: Metadata = { title: "Camera demo" };

export default function CameraDemoPage() {
  return (
    <div className="container page" style={{ gap: 28 }}>
      <header className="prose">
        <p className="eyebrow"><Link href="/demo">Demo</Link> · Option B</p>
        <h1>Try it with your camera</h1>
        <p className="lead">
          Your camera starts only when you press Start camera. Every frame is analysed in this browser tab with the
          same rules as the desktop app, then thrown away. Nothing is recorded or uploaded.
        </p>
        <p className="muted">
          This page downloads the MediaPipe face model (about 4 MB) and its program files from this website. Prefer not
          to use your camera? <Link href="/demo/sample">Explore the sample session.</Link>
        </p>
      </header>
      <CameraDemo />
    </div>
  );
}
