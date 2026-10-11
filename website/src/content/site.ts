/**
 * Site-wide text and links. Edit freely — pages read from here.
 * Only add links that genuinely exist.
 */

export const site = {
  name: "OcuSense",
  tagline: "A study buddy that looks out for your eyes",
  description:
    "OcuSense is a desktop study app for students. It watches your blinks through your webcam, calibrated to you, " +
    "reminds you to take breaks, and makes those breaks fun with games, a little garden and a painting gallery. " +
    "Camera pictures never leave your computer. Not a medical device.",
  /** Verified public repository (checked: HTTP 200). */
  repositoryUrl: "https://github.com/MishkaNastia/OcuSense",
  /** Add a real team contact address here when you have one (leave null to hide it). */
  contactEmail: null as string | null,
};

export const mainNav = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/science", label: "The science" },
  { href: "/demo", label: "Demo" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/about", label: "About us" },
  { href: "/download", label: "Download" },
];

export const footerNav = [
  { href: "/privacy", label: "Privacy" },
  { href: "/accessibility", label: "Accessibility" },
  { href: "/credits", label: "Credits & licences" },
];
