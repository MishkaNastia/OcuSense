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
    status: "available",
    version: "0.1.0",
    url: "https://github.com/MishkaNastia/OcuSense/releases/download/v0.1.0/OcuSense-macOS.zip",
    fileName: "OcuSense for Mac",
    sizeLabel: "195 MB zip · Apple Silicon (M1 or newer)",
    sha256: "02564f1b29097191dfe50aff649fe5c7be837e42cc48270b7ae56a76ea370964",
    verified: [
      "Built and tested on an Apple Silicon Mac.",
      "Not notarised by Apple yet: the first time, right click OcuSense and choose Open.",
    ],
  },
  {
    platform: "Windows (beta)",
    status: "available",
    version: "0.1.0",
    url: "https://github.com/MishkaNastia/OcuSense/releases/download/v0.1.0/OcuSense-windows-x64.zip",
    fileName: "OcuSense for Windows",
    sizeLabel: "204 MB zip · Windows 10 and 11, 64 bit",
    sha256: "31f5d98c668e176b6c8e60812bf6d8e5e3c8fc6f55e29565e6f97a2f1cf230a8",
    verified: [
      "Built and checked automatically on Windows, but not yet tried with a real webcam. Tell us what breaks!",
      "Not signed yet, so SmartScreen may warn: choose More info, then Run anyway.",
    ],
  },
  {
    platform: "Linux (beta)",
    status: "available",
    version: "0.1.0",
    url: "https://github.com/MishkaNastia/OcuSense/releases/download/v0.1.0/OcuSense-linux-x64.tar.gz",
    fileName: "OcuSense for Linux",
    sizeLabel: "286 MB tar.gz · 64 bit (x86_64)",
    sha256: "60d52c2e1e095f019a8a0fc873e661542d594322e03890cd0f7528bda57c475e",
    verified: [
      "Built and checked automatically on Ubuntu, but not yet tried with a real webcam. Tell us what breaks!",
      "Login lasts until you quit.",
    ],
  },
];
