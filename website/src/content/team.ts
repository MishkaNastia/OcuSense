/**
 * Team content for the About us page.
 *
 * Add real members to `members` when you have their consent and details —
 * the page shows them automatically. Leave `photo` empty unless you have a
 * real photo with permission (put it in /public/team/ and use "/team/name.jpg").
 */

export interface TeamMember {
  name: string;
  role: string; // e.g. "Measurement & calibration"
  bio?: string;
  photo?: string;
  link?: { href: string; label: string };
}

export const team = {
  intro:
    "We’re computer science engineering, life sciences engineering and data science students. We built OcuSense " +
    "for a hackathon on student and campus life, mostly because our own eyes were begging us to.",
  approach: [
    { title: "Numbers you can read", text: "Every number has a plain definition and a unit. If we can’t measure something properly, we say so instead of guessing." },
    { title: "Measured against you", text: "A short calibration means OcuSense compares you with yourself, not with some average person." },
    { title: "Breaks people actually take", text: "Telling students to rest doesn’t work. Giving them a garden to water and a gallery to fill works a lot better." },
  ],
  members: [] as TeamMember[],
};
