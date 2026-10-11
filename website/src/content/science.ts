/**
 * "The science behind it": the short home-page summary and the /science page.
 *
 * Every reference below was checked against Crossref (title, authors, journal, DOI).
 * When you add a source, link its DOI and describe only what the paper actually found.
 * Keep the wording careful: these studies show links (associations) in groups of
 * people — they do not mean OcuSense can tell that you personally are tired.
 */

export interface Reference {
  id: string;
  authors: string;
  year: number;
  title: string;
  journal: string;
  doi: string;
}

export const REFERENCES: Reference[] = [
  { id: "patel1991", authors: "Patel, S., Henderson, R., Bradley, L., Galloway, B. & Hunter, L.", year: 1991, title: "Effect of visual display unit use on blink rate and tear stability", journal: "Optometry and Vision Science, 68(11), 888–892", doi: "10.1097/00006324-199111000-00010" },
  { id: "tsubota1993", authors: "Tsubota, K. & Nakamori, K.", year: 1993, title: "Dry eyes and video display terminals", journal: "New England Journal of Medicine, 328(8), 584", doi: "10.1056/NEJM199302253280817" },
  { id: "portello2013", authors: "Portello, J. K., Rosenfield, M. & Chu, C. A.", year: 2013, title: "Blink rate, incomplete blinks and computer vision syndrome", journal: "Optometry and Vision Science, 90(5), 482–487", doi: "10.1097/OPX.0b013e31828f09a7" },
  { id: "sheppard2018", authors: "Sheppard, A. L. & Wolffsohn, J. S.", year: 2018, title: "Digital eye strain: prevalence, measurement and amelioration", journal: "BMJ Open Ophthalmology, 3(1), e000146", doi: "10.1136/bmjophth-2018-000146" },
  { id: "stern1994", authors: "Stern, J. A., Boyer, D. & Schroeder, D.", year: 1994, title: "Blink rate: a possible measure of fatigue", journal: "Human Factors, 36(2), 285–297", doi: "10.1177/001872089403600209" },
  { id: "caffier2003", authors: "Caffier, P. P., Erdmann, U. & Ullsperger, P.", year: 2003, title: "Experimental evaluation of eye-blink parameters as a drowsiness measure", journal: "European Journal of Applied Physiology, 89(3), 319–325", doi: "10.1007/s00421-003-0807-5" },
  { id: "schleicher2008", authors: "Schleicher, R., Galley, N., Briest, S. & Galley, L.", year: 2008, title: "Blinks and saccades as indicators of fatigue in sleepiness warnings: looking tired?", journal: "Ergonomics, 51(7), 982–1010", doi: "10.1080/00140130701817062" },
  { id: "lim2010", authors: "Lim, J. & Dinges, D. F.", year: 2010, title: "A meta-analysis of the impact of short-term sleep deprivation on cognitive variables", journal: "Psychological Bulletin, 136(3), 375–389", doi: "10.1037/a0018883" },
];

/** Why OcuSense focuses on study habits, eye activity and personal feedback (science page). */
export const SCIENCE_WHY = [
  {
    title: "Study habits are personal",
    text:
      "Long study sessions look different for everyone. Generic advice like “take a break every hour” " +
      "ignores how your own focus and comfort change.",
  },
  {
    title: "Eyes carry useful signals",
    text:
      "Blinking and eye closure change during screen work. A webcam can measure some of this without " +
      "special hardware, as long as the measurement is careful and clear about its limits.",
  },
  {
    title: "You are the baseline",
    text:
      "OcuSense compares you with you. A break reminder comes when your blinking slows down compared with " +
      "your own earlier study time, not with a number from a textbook.",
  },
];

/** Three short points for the home page. */
export const SCIENCE_HIGHLIGHTS = [
  {
    title: "Screens change how we blink",
    text: "Studies of computer work found that people blink less, and less completely, while looking at a screen. That pattern is linked to dry, tired feeling eyes.",
  },
  {
    title: "Drowsiness shows in the eyelids",
    text: "As people become drowsy, blinks tend to last longer and the eyes reopen more slowly. Researchers use these blink measures to study fatigue.",
  },
  {
    title: "Fatigue costs focus",
    text: "Lack of sleep and fatigue reduce attention and alertness, so time spent studying while very tired tends to be less effective.",
  },
] as const;

export interface ScienceSection {
  id: string;
  title: string;
  paragraphs: string[];
  sources: string[]; // REFERENCES ids
}

export const SCIENCE_SECTIONS: ScienceSection[] = [
  {
    id: "screens",
    title: "Blinking at a screen",
    paragraphs: [
      "Every blink spreads a fresh tear film over the front of the eye. When we concentrate on a screen we blink noticeably less often: an early study of display work measured a clear drop in blink rate during screen use compared with before it.",
      "Screen work can also change how we blink. Many blinks become incomplete (the lid doesn’t close all the way), and in one study, eye strain symptoms after a reading task were linked to the share of incomplete blinks more than to the total number of blinks. Looking straight ahead at a monitor also leaves more of the eye’s surface exposed, which favours drying.",
      "Reviews of “digital eye strain” describe dryness, tired or sore eyes and blurred vision as common among people who spend long hours at a computer, and list regular breaks among the simple measures that can help.",
    ],
    sources: ["patel1991", "tsubota1993", "portello2013", "sheppard2018"],
  },
  {
    id: "drowsiness",
    title: "What blinking reveals about drowsiness",
    paragraphs: [
      "Blinking is partly automatic, which makes it a useful window on alertness. In laboratory studies, blink rate tended to rise with time spent on a task, and researchers proposed it as a possible measure of fatigue.",
      "The length of each blink appears even more informative. When people became drowsy, their blinks lasted longer, the eyelids closed and reopened more slowly, and the eyes spent more time closed. Studies comparing many eye-movement measures found blink duration to be among the clearest signs of sleepiness.",
    ],
    sources: ["stern1994", "caffier2003", "schleicher2008"],
  },
  {
    id: "effectiveness",
    title: "Why fatigue makes studying less effective",
    paragraphs: [
      "Being tired changes how well you think. A large meta-analysis of sleep deprivation studies found that losing sleep impairs simple attention and vigilance most strongly, and also affects other thinking skills. In practice, the longer you push on while very tired, the less you tend to get out of each extra minute.",
      "A short break (a walk, a stretch, looking into the distance, or real rest) gives your eyes and attention a chance to recover. Which break works best differs from person to person, so OcuSense offers a few kinds and leaves the choice to you.",
    ],
    sources: ["lim2010", "sheppard2018"],
  },
];
