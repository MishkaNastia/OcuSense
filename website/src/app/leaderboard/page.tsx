import type { Metadata } from "next";
import Link from "next/link";

import { HeroArt } from "@/components/art/Art";
import { GAMES, topScores, type Leaderboard } from "@/lib/leaderboard";

import styles from "./leaderboard.module.css";

export const metadata: Metadata = { title: "Leaderboard" };

const day = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

function Board({ board }: { board: Leaderboard }) {
  if (board.status === "not-set-up") return <p className="muted">The leaderboard isn’t connected on this copy of the website.</p>;
  if (board.status === "unavailable") return <p className="muted">The scores can’t be loaded right now. Try again in a minute.</p>;
  if (!board.rows.length) return <p className="muted">No scores yet. The first one to play gets the gold.</p>;
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr><th scope="col">Place</th><th scope="col">Player</th><th scope="col" className={styles.num}>Score</th><th scope="col">When</th></tr>
        </thead>
        <tbody>
          {board.rows.map((r) => (
            <tr key={`${r.place}-${r.username}`} className={r.place <= 3 ? styles.podium : undefined}>
              <td className={`mono ${styles.place}`}>{r.place}</td>
              <td>{r.username}</td>
              <td className={`mono ${styles.num}`}>{r.score.toLocaleString("en-GB")}</td>
              <td className="muted">{day(r.createdAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function LeaderboardPage() {
  const boards = await Promise.all(GAMES.map((g) => topScores(g.id)));
  return (
    <div className="container page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Leaderboard</p>
          <h1>Who blinks best?</h1>
          <p className="lead">
            The best scores from the games in the OcuSense app. Play while you’re logged in and your best round shows up
            here within a few minutes. Only usernames and scores are public: nobody sees your blinks.
          </p>
        </div>
        <HeroArt />
      </header>
      {GAMES.map((game, i) => (
        <section key={game.id} className="section-rule" aria-labelledby={`board-${game.id}`}>
          <h2 id={`board-${game.id}`}>{game.name}</h2>
          <p className="muted">Top 20 for {game.what}.</p>
          <Board board={boards[i]} />
        </section>
      ))}
      <p className="muted">
        Want your name up here? <Link href="/download">Get the app</Link>, make an account on its Log in page and play a round.
      </p>
    </div>
  );
}
