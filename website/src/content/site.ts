/**
 * Site-wide text and links. Edit freely — pages read from here.
 * Only add links that genuinely exist.
 */

export const site = {
  name: "OcuSense",
  tagline: "A study companion that helps you notice your eye patterns",
  description:
    "OcuSense is a personalised study companion. It uses webcam-based eye measurements, calibrated to you, " +
    "to help you notice changes while studying, take breaks, and reflect on what helps you. Not a medical device.",
  /** Verified public repository (checked: HTTP 200). */
  repositoryUrl: "https://github.com/MishkaNastia/OcuSense",
  /** Add a real team contact address here when you have one (leave null to hide it). */
  contactEmail: null as string | null,
};

export const mainNav = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/demo", label: "Demo" },
  { href: "/about", label: "About us" },
  { href: "/download", label: "Download" },
];

export const footerNav = [
  { href: "/science", label: "The science" },
  { href: "/privacy", label: "Privacy" },
  { href: "/accessibility", label: "Accessibility" },
  { href: "/credits", label: "Credits & licences" },
];
