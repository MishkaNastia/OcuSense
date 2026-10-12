# OcuSense: synthetic distribution fitting and model-selection benchmark

A research prototype that asks: **if blink data come from a known probability
distribution, can maximum likelihood plus AIC identify that distribution, and how
reliably?** Synthetic data are generated from known laws, every candidate family
is fitted by maximum likelihood, the candidates are ranked by AIC (with AICc and BIC
reported too), and Monte Carlo replication measures how often the true family is
recovered. This happens under ideal conditions, with missed blinks, with timestamp
noise, at different sample sizes, and in regimes where families nearly coincide.

This package is independent of the webcam app in the parent directory and of any
future FastAPI backend. It has no neural networks, no health classification and no
frontend.

## Install

Python 3.11+.

```bash
cd ocusense-distributions
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Run

```bash
.venv/bin/python -m pytest                                  # correctness tests (171, ~7 s)
.venv/bin/python benchmarks/run_recovery_benchmark.py       # statistical recovery report, PASS/FAIL (~5 min)
.venv/bin/python -m pytest benchmarks                       # same benchmark as pytest checks (~5 min)
.venv/bin/python experiments/run_single.py                  # one dataset per track, 4 plots each
.venv/bin/python experiments/run_benchmark.py --smoke       # 10 reps, n ≤ 300, ~5 s
.venv/bin/python experiments/run_benchmark.py --reps 100    # full benchmark, ~1 min on 14 cores
.venv/bin/python experiments/run_robustness.py --reps 100   # experiments A–D, ~1 min
```

Useful options: `--reps 500` / `--reps 1000`, `--sample-sizes 30 100 300`,
`--n-jobs N`, `--seed S`, `--out DIR`, `--scenarios NAME ...` (benchmark),
`--no-heldout`, and `--n` (robustness sample size for A/B). Every
replicate's seed is derived from `(base seed, scenario, n, replicate, condition)`,
so the same command produces the same numbers regardless of `--n-jobs`.

Outputs go to `results/tables/*.csv` and `results/figures/*.png`.

## Testing: correctness vs statistical recovery

The two kinds of tests are kept apart.

| Suite | Location | What it asserts | Expects 100%? |
|---|---|---|---|
| **Correctness** | `tests/` (`pytest`) | the code does exactly what it should: formulas, parameter counts, failure handling, input immutability, noise models, reproducibility, report bookkeeping | yes, deterministic |
| **Statistical recovery** | `benchmarks/` (`pytest benchmarks` or `run_recovery_benchmark.py`) | how often the true family and parameters are recovered across many random datasets | no |

`benchmarks/run_recovery_benchmark.py` generates 100 datasets per scenario
(24 scenarios, 3 per family) at n = 30, 60, 100, 300, 1000 and 5000. It fits all
candidates and prints:

1. AIC and BIC recovery % per scenario and n, and pooled per family;
2. the most common confusions (true → wrongly selected family, with share);
3. median |relative error| of every parameter of the true family, plus the
   largest biases;
4. count data under **detection noise**:
   `observed = Binomial(X, 1 − q) + Poisson(fp)`, with missed-detection
   probability q ∈ {0.1, 0.2, 0.3}, false positives fp ∈ {0.5, 1, 3} per window,
   and two combinations;
5. PASS/FAIL against a small set of pre-declared floors, with an overall verdict
   and exit code.

Everything in 1–4 is reported, not graded. Only these floors are graded
(rationale in `src/ocusense/recovery.py`):

| Check | Floor | Why |
|---|---|---|
| BIC selection | ≥ 95% at n = 5000, ≥ 75% at n = 1000 | BIC is consistent |
| AIC selection | ≥ 70% at n = 5000 | AIC's nested-model ceiling is ≈ 80% (exponential) |
| Parameter error (true family) | median ≤ 10% at n = 5000, ≤ 20% at n = 1000 | MLE error ∝ 1/√n |
| Count noise: fitted mean | \|bias\| ≤ 1% for n ≥ 1000, every condition | all count MLEs reproduce the sample mean, whose expectation is (1−q)E[X]+fp |
| Count noise: selection and parameters | same floors as clean data, measured against the transformed parameters | only where the family survives the noise: pure thinning (any family) or Poisson + false positives |

The floors are calibrated for 100 datasets per cell. With `--reps 20`, expect
occasional FAILs from Monte Carlo noise alone.

**Latest run** (100 datasets per cell, 72,000 datasets): **681/681 checks PASS.**

* **BIC at n = 5000:** recovery 98–100% for every scenario.
* **AIC:** levels off at 77–79% for exponential and 86–94% for most Poisson, NB and
  ZIP scenarios (nested models), versus 99–100% for ZINB, log-normal, gamma and
  Weibull.
* **Small samples:** at n = 30 the interval families are mostly confused with each
  other, with gamma recovered only 31–33% of the time.
* **Count noise:**
  * Missed detections and false positives barely affect Poisson and NB recovery,
    since NB plus Poisson noise still looks like NB.
  * False positives destroy zero-inflation detection: ZIP is identified 0% of the
    time at n ≥ 1000 with fp ≥ 0.5 per window, and ZINB wins instead.
  * With fp = 3, ZINB becomes NB in 87–91% of datasets.
  * A ZIP/ZINB verdict on real data therefore says as much about the false-positive
    rate as about the person's blinking.

## How the pipeline works

```
synthetic.py      generate_synthetic_data(distribution, parameters, n_samples, seed)
      │           scenarios (24 primary + 10 overlap), renewal-process timestamps
      ▼
noise.py          missed blinks (event deletion / binomial thinning), timestamp jitter
      ▼
fitting.py        fit_distribution(data, name) -> FitResult   (MLE)
      ▼
selection.py      calculate_aic / calculate_aicc / calculate_bic
                  select_best_distribution(data, candidate_names) -> ranked table
      ▼
evaluation.py     Monte Carlo blocks, held-out validation, accuracy / confusion /
                  parameter-recovery summaries, parametric bootstrap
      ▼
visualization.py  all figures
```

`distributions.py` is the single source of truth for every family. The same
definition supplies the sampler, log-likelihood, CDF and reported parameters, so
generation, estimation and reporting cannot use different parameterizations.

### Two tracks, never mixed

| Track | Data | Candidates | Likelihood |
|---|---|---|---|
| A, `count` | blinks per 60 s window (nonnegative integers) | Poisson, negative binomial, ZIP, ZINB | probability mass |
| B, `interval` | interblink intervals in seconds (> 0) | log-normal, gamma, Weibull, exponential | probability density, loc = 0 |

A mass and a density are on different scales, so their AICs are meaningless to
compare. `select_best_distribution` raises `ValueError` if candidates span both
tracks. `rank_fits` also refuses fits whose data fingerprints differ, so AIC values
from different observations cannot be compared by accident. Continuous
distributions are never fitted to integer counts.

## Distributions

All positive-support continuous families have location fixed at 0, and location is
not counted as a parameter.

| Name | Parameters (k) | Definition | SciPy equivalent |
|---|---|---|---|
| `poisson` | λ (1) | P(x) = e^(−λ) λ^x / x! | `poisson(mu=λ)` |
| `negbin` | μ, r (2) | P(x) = Γ(x+r)/(Γ(r) x!) · (r/(r+μ))^r · (μ/(r+μ))^x; E = μ, **Var = μ + μ²/r** | `nbinom(n=r, p=r/(r+μ))` |
| `zip` | λ, π (2) | P(0) = π + (1−π)e^(−λ); P(x>0) = (1−π)·Poisson(x; λ) | — |
| `zinb` | μ, r, π (3) | P(0) = π + (1−π)·NB(0; μ, r); P(x>0) = (1−π)·NB(x; μ, r) | — |
| `lognormal` | μ_log, σ (2) | ln X ~ Normal(μ_log, σ²) | `lognorm(s=σ, scale=e^μ_log)` |
| `gamma` | shape a, scale θ (2) | f(x) = x^(a−1) e^(−x/θ) / (Γ(a) θ^a) | `gamma(a, scale=θ)` |
| `weibull` | shape c, scale λ (2) | f(x) = (c/λ)(x/λ)^(c−1) exp(−(x/λ)^c) | `weibull_min(c, scale=λ)` |
| `exponential` | scale θ (1) | f(x) = e^(−x/θ)/θ | `expon(scale=θ)` |

In ZIP and ZINB, π is the probability of a *structural* zero, e.g. a window where
the eyes were closed or the person was away. The scenarios are defined in
`synthetic.py`, with three parameter settings per family plus ten overlap
regimes.

## How parameters are estimated

* **Poisson:** closed form, λ̂ = x̄.
* **Interval families:** `scipy.stats.<dist>.fit(x, floc=0)`. With location fixed,
  SciPy solves the likelihood equations directly. The tests confirm this agrees with
  a generic optimizer.
* **NB, ZIP, ZINB:** numerical MLE with `scipy.optimize.minimize`. Parameters are
  transformed (log for μ, λ, r; logit for π) and box-bounded. Each fit starts from
  3–4 moment-based starting points, uses L-BFGS-B with tight tolerances, and falls
  back to Powell if L-BFGS-B doesn't report convergence. The best converged start
  is kept. Log-pmfs use `gammaln`, `log1p`, `xlogy` and `logaddexp` for stability.
  Counts are compressed to (value, multiplicity) pairs before optimization.

**Failures are reported, never patched.** If no start converges, or the likelihood
is non-finite, the `FitResult` has `status="failed"`, empty `params`, NaN
log-likelihood and the optimizer messages. Failed fits stay in the ranking table
(at the bottom, NaN AIC, weight 0). No moment estimate is substituted. Degenerate
inputs are handled explicitly:

* All-zero counts: Poisson gives λ̂ = 0, flagged as boundary. NB, ZIP and ZINB
  fail as non-identifiable.
* Constant intervals: two-parameter families fail; exponential is still fine.

Invalid inputs raise `ValueError`: negative or non-integer counts, non-positive
intervals, NaN, or arrays that aren't 1-D. The input array is never modified.

In the full benchmark (48,000 fits) **no fit failed**.

### Identifiability and boundary fits

Several candidates contain others as limits:

* **NB → Poisson as r → ∞.** If the sample variance doesn't exceed the mean, the NB
  likelihood keeps increasing in r, so r̂ is effectively infinite and not
  identifiable. NB then ties Poisson in log-likelihood and loses on AIC by exactly
  2.
* **ZIP → Poisson and ZINB → NB at π = 0.** With no excess zeros, π̂ sits at 0.
* **ZINB → ZIP as r → ∞.**
* **Gamma(shape = 1) = Weibull(shape = 1) = Exponential, exactly.**

Fits that end at such a boundary (r̂ > 10⁴, π̂ < 10⁻⁴, or on an optimizer bound)
get `status="boundary"` and an explanatory message. They are genuine MLEs, so they
stay in the ranking. In the benchmark, the boundary rate on Poisson data was 96% for
ZIP and 98% for ZINB, which shows how often the extra parameters are simply unused.

## Interpreting AIC

* AIC = 2k − 2 log L, AICc = AIC + 2k(k+1)/(n−k−1) (∞ when n ≤ k+1),
  BIC = k log n − 2 log L.
* Only **differences** matter: ΔAIC_i = AIC_i − min AIC. As a rule of thumb, ΔAIC ≤ 2
  means the data barely separate the two models, and ΔAIC > 10 means essentially no
  support relative to the best.
* **Akaike weights** w_i = exp(−ΔAIC_i/2) / Σ exp(−ΔAIC_j/2) express *relative*
  support within the candidate set. They are **not** probabilities that a model is
  literally true. If the truth isn't in the set, the weights still sum to 1.
* **AIC is not consistent for nested models.** When the simpler model is true, a
  larger nested competitor wins whenever its likelihood-ratio statistic exceeds 2.
  For one extra interior parameter that happens with probability
  P(χ²₁ > 2) ≈ 0.157. For a boundary parameter (r → ∞, π = 0) it is about half
  that, ≈ 0.079. Accuracy for a true *simpler* model therefore levels off below 1
  as n grows. Exponential data have two such competitors (gamma, Weibull), giving an
  expected ceiling around 0.80–0.84. The benchmark shows 0.82. Poisson data plateau
  near 0.91. This is the criterion working as designed, not a bug. BIC's log n
  penalty removes this ceiling (experiment C).

## Results (100 replicates per cell; `results/tables`)

### Benchmark: exact family recovery by AIC, pooled over three scenarios per family

| true family | n=30 | 100 | 300 | 1000 | 5000 |
|---|---|---|---|---|---|
| Poisson | 0.96 | 0.91 | 0.91 | 0.92 | 0.91 |
| Negative binomial | 0.85 | 0.99 | 0.97 | 0.93 | 0.94 |
| ZIP | 0.93 | 0.95 | 0.94 | 0.93 | 0.93 |
| ZINB | 0.84 | 1.00 | 1.00 | 1.00 | 1.00 |
| Log-normal | 0.59 | 0.78 | 0.90 | 0.97 | 1.00 |
| Gamma | 0.30 | 0.64 | 0.85 | 0.96 | 1.00 |
| Weibull | 0.51 | 0.72 | 0.86 | 0.95 | 1.00 |
| Exponential | 0.70 | 0.77 | 0.84 | 0.83 | 0.82 |

* **Count models** are well separated even at n = 30, because overdispersion and
  zero inflation are strong signals at blink-rate means (μ ≈ 15).
* **Interval families** need several hundred intervals. At n = 30 a Gamma sample is
  identified only 30% of the time, and log-normal, Gamma and Weibull are confused
  with one another. Thirty intervals is only about 2 minutes of blinking.
* **Plateaus** below 1 for Poisson, NB, ZIP and exponential are the nested-model
  effect explained above.
* **Parameter recovery** error falls roughly as 1/√n for every family
  (`benchmark_parameter_recovery.png`). The dispersion r and the inflation π are the
  hardest parameters: median relative error ≈ 25–35% at n = 30 and ≈ 2% at n = 5000.

### Held-out validation (70/30 random split, AIC from training data only)

The AIC-selected model is within 1 log-likelihood unit of the best held-out model in
90–98% of count datasets and 80–97% of interval datasets, improving with n.
*Exact* agreement is lower (37–84%) because nested candidates often have held-out
log-likelihoods differing by hundredths, so which one is "best on test" is a coin
flip.

### Robustness (n = 300 unless stated)

**A. Missed blinks** (each blink missed independently with probability q):

| true family | q=0 | 0.05 | 0.1 | 0.2 | 0.3 |
|---|---|---|---|---|---|
| Poisson / NB / ZIP / ZINB | 0.94 / 0.98 / 0.94 / 1.00 | — | — | — | 0.98 / 0.94 / 0.98 / 1.00 |
| Log-normal | 0.93 | 0.99 | 1.00 | 1.00 | 1.00 |
| Gamma | 0.89 | 0.90 | 0.78 | 0.58 | 0.46 → log-normal |
| Weibull | 0.82 | 0.67 | 0.52 | 0.35 | 0.16 → gamma |
| Exponential | 0.89 | 0.80 | 0.88 | 0.81 | 0.78 |

* **Counts:** binomial thinning keeps every count family, with the rate scaled by
  (1 − q) and r and π unchanged. Family identification is unaffected. The **rate
  estimate is biased by exactly −q** (estimated 15 → 10.5 at q = 0.3), matching the
  theory line in `robustness_missed_blinks_bias.png`.
* **Intervals:** a missed blink merges two intervals, so observed intervals are
  geometric sums. The exponential family survives (scale → scale/(1 − q), confirmed).
  Gamma and Weibull do not, and missed blinks push selection toward heavier-tailed
  families (Weibull → Gamma → log-normal). **A log-normal fit on real data may partly
  reflect missed detections.**

**B. Timestamp noise** (Gaussian jitter on timestamps, re-sorted, detections
< 50 ms apart merged). Recovery declines only modestly up to σ ≈ 0.1 s, a typical
frame-level jitter (log-normal 0.92 → 0.83, Gamma 0.93 → 0.82), and collapses for log-normal and Gamma at σ = 0.5 s. At that level, noise
makes the intervals more symmetric and Weibull wins almost everything.

The 50 ms merge rule alone, at σ = 0, removes 1.7% of events from Exponential(3 s)
data, matching P(X < 0.05) = 1.65%. That left-truncation is enough for Gamma to beat
Exponential in 37% of datasets. Any real detector has such a refractory period, so
**a pure exponential (Poisson-process) model for intervals is not expected to fit
real data near zero.**

**C. Sample size: AIC vs AICc vs BIC.** For non-nested confusions (log-normal vs
Gamma vs Weibull) all three criteria behave identically, because they have equal k.
For nested truths BIC is clearly better at large n: exponential 0.78 (AIC) vs 1.00
(BIC) at n = 5000, and Poisson 0.97 vs 0.99. AICc differs from AIC only at small n (n ≤ 100).

**D. Overlap regimes** (`robustness_overlap.png`):

* **Gamma(1) and Weibull(1)** are exactly exponential. AIC picks the nominal family
  only 6–13% of the time, but picks *a family that contains the true law* 82–100% of
  the time, mostly Exponential, the most parsimonious correct answer. Low "exact"
  recovery here is the correct behaviour.
* **NB with r = 200** (variance/mean 1.075) needs n ≈ 5000 for reliable detection
  (0.08 at n = 30 → 0.99 at n = 5000). **r = 1000** is still called Poisson 74% of
  the time at n = 5000.
* **ZIP with π = 0.01** is missed at n = 30 (0.29), because most samples contain no
  structural zero at all.
* **ZINB with r = 500** is called ZIP 54–97% of the time; the extra dispersion is
  invisible.

None of these indicate a defect. The data genuinely don't carry enough information
to separate the families.

## Figures

| File | Content |
|---|---|
| `single_{count,interval}_fit.png` | observed PMF/histogram, fitted curves, true law dashed |
| `single_{count,interval}_aic.png` | ΔAIC per candidate, lowest-AIC highlighted, AIC and weights labelled |
| `single_{count,interval}_diagnostics.png` | Q–Q: fitted quantiles (intervals); randomized quantile residuals vs N(0,1) (counts, valid for discrete data) |
| `single_{count,interval}_recovery.png` | estimate ÷ truth with parametric-bootstrap 95% intervals |
| `benchmark_confusion_matrices.png` | true vs selected family at n = 30, 300, 5000 |
| `benchmark_accuracy_vs_n.png` | exact recovery vs n with Wilson 95% bands |
| `benchmark_parameter_recovery.png` | median relative error vs n |
| `benchmark_heldout.png` | training-AIC choice vs held-out log-likelihood |
| `robustness_missed_blinks.png`, `robustness_missed_blinks_bias.png` | experiment A |
| `robustness_timestamp_noise.png` | experiment B |
| `robustness_sample_size.png` | experiment C |
| `robustness_overlap.png` | experiment D |

## Tables

| File | Content |
|---|---|
| `model_selection_results.csv` | full ranked table (parameters, log L, k, AIC, AICc, BIC, ΔAIC, weight, status, message) for the single-dataset examples |
| `benchmark_accuracy.csv` | per scenario × n: accuracy (AIC/AICc/BIC) with Wilson CI, equivalent-family accuracy, share with ΔAIC ≤ 2, mean/median ΔAIC of the truth, selection frequencies, failure rates |
| `benchmark_accuracy_by_family.csv` | the same, pooled by family |
| `confusion_matrices.csv` | long format |
| `parameter_recovery.csv` | bias, mean/median absolute error, RMSE, relative errors, boundary rate |
| `robustness_results.csv` | experiments A–D (`experiment`, `factor`, `level` columns) |
| `robustness_parameters.csv` | parameter bias under A/B, with theoretical expectation where it exists |
| `heldout_results.csv`, `fit_status_rates.csv`, `*_raw.csv`, `benchmark_fits.csv`, `benchmark_replicates.csv` | supporting detail |

## Assumptions and limitations

* **Independence.** Observations are i.i.d.: intervals form a renewal process and
  window counts are independent. Real blinking has serial dependence (fatigue,
  reading vs conversation, time of day). For real sequences, use chronological rather
  than random train/test splits, and expect AIC to favour more complex models,
  because the effective sample size is smaller than n.
* **The truth is in the candidate set.** Here it always is. With real data it
  almost certainly is not, and AIC then selects the best *approximation* among the
  candidates. Report Akaike weights and ΔAIC rather than a single winner.
* **Stationarity.** One parameter set per dataset. Mixtures across people or
  sessions (heterogeneity) look like overdispersion and favour NB or log-normal.
* **Count windows are treated as independent of the interval process.** The count
  track is simulated directly from count laws, not by binning renewal processes.
  Only a Poisson process (exponential intervals) gives Poisson counts. Gamma
  intervals with shape > 1 give under-dispersed counts.
* **Missed blinks are independent of everything.** Real misses cluster, for example
  during head turns or poor lighting. Spurious detections (false positives) are not
  simulated.
* **The timestamp merge threshold (50 ms) is a modelling choice.** It is documented
  and adjustable (`min_separation`).
* **Nested-model plateaus.** "Exact recovery" undercounts success whenever families
  nest or overlap. Read it together with `equivalent_accuracy_aic`,
  `true_within_2_aic` and the confusion matrices.

## Using real OcuSense data

The webcam app (`../blink_counter.py`) knows a blink happened when
`BlinkCounter.update()` returns `True`. To collect data, record a monotonic
timestamp at that moment (e.g. `time.monotonic()`) and save them per session. Also
save the session start and end, and mark paused or uncalibrated periods so they
aren't mistaken for long intervals or zero counts.

```python
import numpy as np
from ocusense.noise import counts_from_timestamps, intervals_from_timestamps
from ocusense.selection import select_best_distribution
from ocusense.distributions import COUNT_FAMILIES, INTERVAL_FAMILIES

ts = np.sort(np.loadtxt("session_blink_times.txt"))       # seconds since session start
duration = 1800.0                                          # session length (s)

intervals = intervals_from_timestamps(ts)                  # Track B
counts = counts_from_timestamps(ts, window=60.0, duration=duration)   # Track A

print(select_best_distribution(intervals, INTERVAL_FAMILIES))
print(select_best_distribution(counts, COUNT_FAMILIES))
```

Practical guidance from the benchmark:

* **Intervals:** aim for at least 300 per person per condition (≈ 20 minutes)
  before trusting a family choice.
* **Counts:** 60-second windows give only 30 observations from a 30-minute session.
  That is enough to detect overdispersion or zero inflation at typical blink rates,
  but not subtle ones.
* **Do not pool** sessions or people into one fit without considering heterogeneity.
* **Expect lower blink rates** if detection misses blinks: the count rate is biased
  by the miss probability.
* **Split chronologically** for held-out validation of time-ordered real data.
