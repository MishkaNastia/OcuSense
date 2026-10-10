/**
 * Download configuration — the ONLY place to edit release details.
 *
 * Status meanings:
 *  - "available":   a real, web-hosted build exists. `url` must be a public https URL
 *                    (e.g. a GitHub Release asset). Never a path on someone's computer.
 *  - "coming-soon": we build it, but no public download exists yet.
 *  - "planned":     not built yet.
 *
 * Only fill in facts you have verified (signing, notarisation, chips, macOS version).
 *
 * Current facts (checked when this site was built):
 *  - OcuSense.app builds locally with ./packaging/build_mac.sh (PyInstaller).
 *  - It is ad-hoc signed only: NOT signed with an Apple Developer ID and NOT notarised.
 *  - It has only been built and run on an Apple Silicon Mac; other Macs are untested.
 *  - It is not hosted anywhere public, so there is no download link yet.
 */

export type ReleaseStatus = "available" | "coming-soon" | "planned";

export interface Release {
  platform: string;
  status: ReleaseStatus;
  version?: string;
  url?: string; // public https URL to the file
  fileName?: string;
  sizeLabel?: string; // e.g. "380 MB"
  sha256?: string;
  /** Verified facts only, shown as a list. */
  verified?: string[];
  notes?: string;
}

export const releases: Release[] = [
  {
    platform: "macOS",
    status: "coming-soon",
    verified: [
      "Builds as a Mac app from the source code (Python, PySide6, MediaPipe).",
      "Built and run so far on an Apple Silicon Mac only.",
      "Not yet signed with an Apple Developer ID or notarised — macOS will warn before opening it.",
    ],
    notes: "We will publish a download here once a build is hosted publicly.",
  },
  { platform: "Windows", status: "planned" },
  { platform: "Linux", status: "planned" },
];
