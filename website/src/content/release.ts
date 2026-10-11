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
 *  - Windows: the same code is prepared for Windows (packaging/build_windows.py and a manual
 *    GitHub Actions build), but no Windows build has been tested on a Windows PC yet.
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
      "Builds as a Mac app from the source code.",
      "Built and run so far on an Apple Silicon Mac only.",
      "Not yet signed with an Apple Developer ID or notarised, so macOS will warn before opening it.",
    ],
    notes: "We’ll put a download here once a build is hosted publicly.",
  },
  {
    platform: "Windows (beta)",
    status: "coming-soon",
    verified: [
      "Same app and code as the Mac version, as a portable folder for Windows 10 and 11 (64 bit).",
      "Built and checked automatically on Windows, but not yet tried with a real webcam. Tell us what breaks!",
    ],
    notes: "Beta: the download appears here once the first build is published.",
  },
  {
    platform: "Linux (beta)",
    status: "coming-soon",
    verified: [
      "Same app and code, as a portable folder for 64 bit Linux (x86_64).",
      "Built and checked automatically on Ubuntu, not yet tried with a real webcam. Login lasts until you quit.",
    ],
    notes: "Beta: the download appears here once the first build is published.",
  },
];
