import { cacheLife } from "next/cache";

import { authConfig } from "@/lib/auth/config";

/** The games with leaderboards (the same ids the app uses in supabase/schema.sql). */
export const GAMES = [
  { id: "blink_code_challenge", name: "Blink Code", what: "90 second Morse code challenge, typed with your blinks" },
  { id: "eye_runner", name: "EyeGame", what: "the endless runner you play by blinking" },
] as const;

export interface LeaderboardRow {
  place: number;
  username: string;
  score: number;
  createdAt: string;
}

export interface Leaderboard {
  status: "ok" | "not-set-up" | "unavailable";
  rows: LeaderboardRow[];
}

/**
 * Top scores for one game, everyone's best score each. Public data only (usernames and
 * scores), read with the publishable key, cached for a few minutes so a busy page
 * doesn't hit the database on every visit.
 */
export async function topScores(game: string, limit = 20): Promise<Leaderboard> {
  "use cache";
  cacheLife("minutes");
  const config = authConfig();
  if (!config) return { status: "not-set-up", rows: [] };
  try {
    const response = await fetch(`${config.url}/rest/v1/rpc/game_leaderboard`, {
      method: "POST",
      headers: { apikey: config.key, "Content-Type": "application/json" },
      body: JSON.stringify({ game_name: game, scope: "everyone", max_rows: limit }),
    });
    if (!response.ok) return { status: "unavailable", rows: [] };
    const data = (await response.json()) as { place: number; username: string; score: number; created_at: string }[];
    return {
      status: "ok",
      rows: data.map((r) => ({ place: Number(r.place), username: r.username, score: r.score, createdAt: r.created_at })),
    };
  } catch {
    return { status: "unavailable", rows: [] };
  }
}
