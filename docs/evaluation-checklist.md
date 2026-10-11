# Manual evaluation checklist

The automatic tests (`python -m unittest`) check the maths and the rules.
They cannot check how well the webcam pipeline works on real people. This
checklist is for that.

**Ground rules**
- Only test with people who agree to it. The app does not record or upload
  anything, and you should not either: write down numbers, not videos.
- Every person does their **own** calibration first (SPACE). There are no
  built-in thresholds for any group of people, and results from a few
  testers do not prove the counter works for everyone.
- "Personal eye openness" only means "how open, compared with this person's
  own calibration". It is not a measure of tiredness or health.

## How to run one trial

1. Start the app, press SPACE, follow the calibration.
2. Note the number on screen ("Blinks: N").
3. The tester blinks a known number of times (e.g. 10), counting out loud
   or with a helper counting.
4. Note the new number. Record **expected** vs **counted**.
5. Also note: any calibration failures (and the message), and how often
   "measurement paused" appeared.

## Conditions to cover

Try to cover as many rows as you can, with several different people.
For every row, also do the two "should not count" checks at the bottom.

### People
- [ ] Different eye shapes and sizes (e.g. narrower / rounder eyes,
      hooded or monolid eyelids, deep-set eyes)
- [ ] A range of skin tones
- [ ] Different eyebrow/eyelash appearance and with/without eye makeup
- [ ] Someone whose two eyes open to noticeably different amounts

### Glasses
- [ ] No glasses
- [ ] Regular glasses (thin and thick frames)
- [ ] Glasses with a strong reflection from the screen or a window
- [ ] Sunglasses or tinted lenses (expected to fail or pause - check it
      pauses or rejects calibration instead of counting nonsense)

### Lighting
- [ ] Normal indoor light, facing the light
- [ ] Dim room
- [ ] Strong light from behind (window behind the person)
- [ ] Light from one side only (half the face in shadow)
- [ ] Coloured/changing light (e.g. only the screen lighting the face)

### Head position and movement
- [ ] Sitting normally, facing the camera
- [ ] Close to the camera / far from the camera
- [ ] Head turned left and right (should show "measurement paused" when
      turned a lot)
- [ ] Head tilted sideways
- [ ] Looking down (e.g. at a keyboard) - EAR can drop when looking down,
      so watch for false blinks here
- [ ] Talking, smiling, laughing while blinking
- [ ] Moving around while blinking

### Should NOT count
- [ ] Keeping eyes closed for 3+ seconds counts as **one** blink
- [ ] A one-eyed wink counts as **zero**
- [ ] Squinting (eyes narrowed, not closed) counts as **zero**
- [ ] Closing eyes, covering the camera, uncovering with open eyes counts
      as **zero** (tracking lost resets the half-finished blink)

### Calibration
- [ ] Not closing eyes in the "closed" step is **rejected**
- [ ] Moving the head a lot during calibration is **rejected** or works
      after retrying
- [ ] Pressing C recalibrates; the blink total is kept

## Results table

| Tester (anonymous ID) | Condition | Expected blinks | Counted | Calibration retries | Notes |
|---|---|---|---|---|---|
| T1 | normal light, no glasses | 10 | | | |
| | | | | | |

When summarising, report results **per condition** (e.g. "8/10 in dim
light"), and say how many people and conditions were tested. Don't claim
the counter is accurate for situations you didn't test.
