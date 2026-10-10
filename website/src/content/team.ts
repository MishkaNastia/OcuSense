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
    "We are a team of computer science engineering, life sciences engineering and data science students building OcuSense for a hackathon " +
    "on student and campus life.",
  approach: [
    { title: "Understandable measurements", text: "Every number has a plain definition, a unit, and a note on its precision." },
    { title: "Personal calibration", text: "Measurements are relative to your own open and closed eyes, not a population average." },
    { title: "Your feedback in the loop", text: "Self-reported check-ins stay separate from camera measurements, and are labelled as such." },
  ],
  members: [] as TeamMember[],
};
