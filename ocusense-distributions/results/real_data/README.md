# Real blink data: which distribution fits?

This folder holds the results of testing which candidate distribution best describes
real blinks from the Artwork Gallery eye-tracking dataset in `../../../data/`.
Everything here is produced by
[`experiments/run_real_data.py`](../../experiments/run_real_data.py).

## Answer

| Track | Group | n | Best | vs runner-up | Does it fit? |
|---|---|---|---|---|---|
| Interblink interval | P1 | 176 | log-normal | better than gamma (Vuong p = 0.001) | no (p = 0.002), no family fits |
| | P2 | 129 | log-normal | tied with gamma (p = 0.56) | no (p = 0.008), only gamma passes |
| | P3 | 203 | log-normal | tied with gamma (p = 0.35) | no (p = 0.002), no family fits |
| | All | 508 | log-normal | better than gamma (p = 0.002) | no (p = 0.002), no family fits |
| Blinks per 60 s | P1 | 8 | Poisson | extra parameters not needed | yes, as do all four |
| | P2 | 11 | Poisson | extra parameters not needed | yes, as do all four |
| | P3 | 9 | Poisson | extra parameters not needed | yes, as do all four |
| | All | 28 | negative binomial | tied with Poisson (LR p = 0.051) | yes, as do all four |

**Intervals:** of the four candidates, log-normal is closest to the data. It is
clearly better than gamma for P1 and the pooled data, and tied with gamma for P2 and
P3. The goodness-of-fit test still **rejects log-normal everywhere**. The candidates
can be ranked, but none of them describes the data exactly.

**Counts:** with only 8–28 one-minute windows, the test can't reject any family.
Poisson wins because it is the simplest, not because the data show it to be right.

## 1. The data

* **Source:** Klötzl et al., *NMF-Based Analysis of Mobile Eye-Tracking Data*,
  ETRA '24 ([doi:10.1145/3649902.3653518](https://doi.org/10.1145/3649902.3653518)).
  Recorded with Pupil Labs head-mounted eye trackers and exported from Pupil Cloud.
* **Task:** 3 participants (P1–P3) looked at 5 paintings and their text plaques in a
  set order. There are 27 recordings (R01–R27), 9 per participant, each 45–190 s long.
  That gives 42 minutes in total.
* **What was used:** blink start and end times from `blinks.csv`. Recording length
  is taken from the first and last timestamps in `gaze.csv`.

## 2. Preparing the data

1. **Blink onsets.** Each blink's start time, in seconds since the first gaze sample.
2. **Merge split blinks.** The headset detector often records one blink as two rows
   only 4–8 ms apart. If a blink starts less than **100 ms** after the previous one
   ends, the two are counted as one. This takes the total from 590 to **535 blinks**.
3. **Two tracks**, as defined in the package README:
   * **Intervals:** time from one blink onset to the next, within a recording only.
     This gives 508 intervals (P1 176, P2 129, P3 203).
   * **Counts:** blinks per complete 60 s window. This gives 28 windows (P1 8, P2 11,
     P3 9).
4. Each track is tested **per participant** and **pooled** across all three.

## 3. The tests

Each dataset goes through three steps. The significance level is α = 0.05.

1. **Which candidate is best?** Every family on the track is fitted by maximum
   likelihood (`fit_candidates`) and ranked by AIC (`rank_fits`). The lowest AIC is
   "best".
2. **Is it really better than the runner-up?**
   * If one model is a special case of the other (for example Poisson inside negative
     binomial, or exponential inside gamma), a **likelihood-ratio test** checks
     whether the extra parameters help.
   * Otherwise (for example log-normal vs gamma) a **Vuong test** checks whether one
     model's per-observation likelihood is consistently higher.
   * p ≥ α means the data can't tell the two models apart.
3. **Does it actually fit?** A **parametric-bootstrap Kolmogorov-Smirnov test** is
   used. It measures the largest gap between the data's cumulative distribution and
   the fitted model's. The gap is then compared with the gaps obtained by simulating
   500 datasets from the fitted model and refitting each one. Refitting corrects for
   the parameters having been estimated from the same data, which a plain KS test
   ignores. p < α rejects the model.

AIC on its own only ranks the candidates. Step 3 is what shows whether the winner
actually fits.

## 4. Why log-normal is rejected

The logs of the intervals are flatter than a normal curve, so both ends of the
distribution are thinner than log-normal predicts:

* **No very short gaps:** no interval is shorter than about 0.6 s, but log-normal
  expects about 1% below 0.37 s. A blink lasts about 0.35 s and merging removes gaps
  under 0.1 s, so this is a real floor.
* **No very long gaps:** the 99th percentile is about 21 s, against 24 s predicted.
  Recordings last at most about 3 minutes, which limits how long a gap can be.
* **Too many 1.0–1.4 s gaps:** this could be two blinking modes mixed together, such
  as reading plaques versus looking at paintings, or a mix of three people.

## 5. Caveats

* **The merge rule matters.** Without merging (`--merge-ms 0`), P2 switches to
  exponential and the pooled data split between log-normal (AIC) and exponential (BIC).
* **Other effects can favour log-normal.** The package's robustness experiments show
  that missed blinks and pooling different people or conditions both push selection
  toward log-normal.
* **The sample is small.** The package README recommends at least 300 intervals per
  person, and each participant here has 129–203.
* **The likelihood-ratio p-values are conservative** when the larger model's extra
  parameter sits at its boundary (r → ∞ or π = 0). The correct p is roughly half,
  which would make the pooled NB-vs-Poisson result about 0.025.
* **The tests assume independent intervals.** Real blinking changes with the task,
  so the effective sample size is smaller than n.

## 6. Files

| File | Content |
|---|---|
| `tables/real_verdicts.csv` | one row per track × group: best family and its parameters, runner-up, ΔAIC, comparison test and p, goodness-of-fit p, verdict |
| `tables/real_candidates.csv` | every candidate: parameters, AIC, ΔAIC, Akaike weight, goodness-of-fit p, fit status |

## 7. Reproduce

```bash
cd ocusense-distributions
.venv/bin/python experiments/run_real_data.py      # about 2 min
```

Options: `--merge-ms` (default 100), `--window` (count window in s, default 60),
`--n-boot` (bootstrap datasets per test, default 500), `--alpha` (default 0.05),
`--seed`, `--out`. The script prints one verdict line per dataset and rewrites the two
tables. It doesn't change this README.
