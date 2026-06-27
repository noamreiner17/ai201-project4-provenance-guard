# ai201-project4-provenance-guard

## Project Overview

Provenance Guard is a backend service that helps determine whether a piece of text is likely AI-generated or human-written. Instead of making a simple yes/no decision, the system combines multiple detection signals to produce a confidence score and a transparency label. The goal is to provide useful information to readers while allowing creators to appeal decisions that may be incorrect.

Every classification is stored in a structured audit log, and creators can appeal decisions they believe are incorrect.

---

## Architecture Overview

When a creator submits text, the request is first received by the `POST /submit` API endpoint and validated. The text is then analyzed by two independent detection signals:

1. **LLM-Based Classification (Groq)** – Uses an LLM to estimate whether the writing appears AI-generated or human-written based on semantic patterns and writing style.
2. **Stylometric Analysis** – Measures statistical writing characteristics such as sentence length variation, vocabulary diversity, and punctuation usage.

The outputs from both signals are combined into a single confidence score. Based on this score, the system generates one of three transparency labels:

- **Likely AI-Generated**
- **Likely Human-Written**
- **Uncertain Result**

The final decision, confidence score, individual signal scores, and metadata are stored in the audit log before the API returns the response to the user.

If a creator disagrees with the decision, they may submit an appeal through the `POST /appeal` endpoint. The appeal is linked to the original submission, its status changes to **Under Review**, and the appeal is recorded in the audit log.

### Architecture Diagram

```text
                   POST /submit
                         |
                         v
                 Validate Request
                         |
          +--------------+--------------+
          |                             |
          v                             v
    Groq LLM Signal          Stylometric Analysis
          |                             |
          +--------------+--------------+
                         |
                         v
              Confidence Scoring
                         |
                         v
              Transparency Label
                         |
                         v
                Structured Audit Log
                         |
                         v
                JSON API Response


                   POST /appeal
                         |
                         v
                 Update Status
                "Under Review"
                         |
                         v
                Structured Audit Log
                         |
                         v
                   JSON Response
```

---

## Setup

1. Create / activate a virtual environment and install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Provide a Groq API key in a `.env` file in the project root:

   ```text
   GROQ_API_KEY=your_key_here
   ```

3. Run the app:

   ```bash
   python app.py
   ```

   The server starts on `http://localhost:5000`.

---

## Detection Signals

Each signal produces a normalized score between **0.0** and **1.0**:

- **0.0 = Strongly Human**
- **1.0 = Strongly AI**

### Why these two signals?

The two signals were chosen because they fail in *different* ways, and combining
them is more robust than either alone. The Groq LLM is a **semantic** detector: it
reads meaning, tone, and the hard-to-quantify "feel" of machine writing (hedging,
generic framing, absence of lived detail). The stylometric signal is a **mechanical**
detector: it never reads meaning at all, only counts — sentence-length spread,
vocabulary repetition, punctuation rate. A purely statistical detector misses
AI text that is statistically ordinary; a purely LLM-based detector is a black box
that can be confidently wrong with no inspectable reason. Pairing a meaning-based
signal with a math-based one means a misfire in one can be tempered by the other,
and the stylometric metrics give a transparent, auditable number to sit beside the
LLM's opaque judgment. The two are deliberately *not* the same kind of detector.

### Signal 1 — Groq LLM

The Groq API analyzes overall writing style, sentence coherence, vocabulary and word choice, consistency of tone, and common AI writing patterns. It returns a single confidence score between 0.0 and 1.0.

**Limitations:** can misclassify polished human writing, and can be fooled by heavily edited AI-generated text.

### Signal 2 — Stylometric Analysis

The backend computes three measurable writing statistics, normalizes each to [0.0, 1.0] where higher = more AI-like, and averages them:

- **Sentence length variance** — uniform sentence lengths read as AI-like; varied lengths read as human.
- **Type-Token Ratio (vocabulary diversity)** — repetitive vocabulary reads as AI-like; diverse vocabulary reads as human.
- **Punctuation frequency** — steady, structural punctuation reads as polished/AI-like.

```text
Stylometric Score = (variance_score + ttr_score + punctuation_score) / 3
```

**Limitations:** poems and song lyrics may produce misleading statistics; very short text does not contain enough information for reliable analysis; technical writing may appear overly consistent despite being human-written. In practice this signal is the weaker of the two on short inputs (Type-Token Ratio is naturally high at short lengths and barely discriminates), so it tends to nudge the Groq verdict rather than drive it.

---

## Confidence Scoring

Both signals contribute equally:

```text
Final Confidence = (Groq Score + Stylometric Score) / 2
```

The resulting confidence score ranges from **0.0** to **1.0** and maps to an attribution and a transparency label:

| Confidence Score | Attribution     | Transparency Label    |
| ---------------: | --------------- | --------------------- |
|      0.00 – 0.25 | `human`         | Likely Human-Written  |
|      0.26 – 0.45 | `likely_human`  | Likely Human-Written  |
|      0.46 – 0.54 | `uncertain`     | Uncertain Result      |
|      0.55 – 0.75 | `likely_ai`     | Likely AI-Generated   |
|      0.76 – 1.00 | `ai`            | Likely AI-Generated   |

Because false positives are more harmful than false negatives, the system prefers returning **Uncertain** rather than making an incorrect high-confidence prediction.

### Why a simple average?

The scoring is a plain equal-weight average rather than a learned or weighted
combination, and that is a deliberate choice for this stage. With only two signals
and no labeled training data, any weighting would be guessed, not measured —
inventing a `0.7 / 0.3` split would imply a precision the system has not earned.
An equal average is honest about that: both signals are treated as equally
trustworthy because there is no evidence to rank them. It is also fully transparent
— every score in the audit log can be re-derived by hand from the two signal scores,
which matters for a tool whose whole purpose is accountable, appealable decisions.

The narrow **Uncertain** band (`0.46 – 0.54`) is the other half of the design. When
the two detectors disagree (e.g. Groq says `0.9` AI, stylometry says `0.17` human),
the average lands near the middle and the system declines to make a confident call.
This is intentional: a hedged "we're not sure" is the correct, least-harmful output
when the evidence genuinely conflicts.

### Example submissions — confidence varies meaningfully

These are real scores pulled from `audit_log.jsonl` during Milestone 4 testing,
showing that the scoring produces genuine variation rather than a constant:

| Case                       | Groq | Stylometric | **Confidence** | Label                |
| -------------------------- | ---: | ----------: | -------------: | -------------------- |
| **High-confidence** (human)| 0.20 |      0.0824 |     **0.1412** | Likely Human-Written |
| **Lower-confidence** (AI)  | 0.80 |      0.49   |     **0.645**  | Likely AI-Generated  |

The casual, informal human sample scored **0.1412** — both signals strongly agreed
it was human (varied sentence length, lowercase, irregular punctuation), so the
result is far from the uncertain band and the label is confident. The AI-leaning
sample scored **0.645** — Groq was fairly sure (0.80) but stylometry was only
mildly AI-leaning (0.49), so they partially disagreed, dragging the combined score
down toward the middle. It still lands as "Likely AI-Generated," but much closer to
the Uncertain boundary, which honestly reflects that the two signals were not in
full agreement. The ~0.50-point spread between the two cases is exactly the kind of
meaningful variation the scoring is meant to produce.

### Transparency Label Variants

The confidence score maps to one of three transparency labels. Each is returned with a short `label` title and a fuller `label_detail` explanation:

| Confidence    | `label`              | `label_detail`                                                                                                                                          |
| ------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `0.00 – 0.45` | Likely Human-Written | Our system found strong evidence that this content was written by a human author. Confidence: High.                                                    |
| `0.46 – 0.54` | Uncertain Result     | Our system could not confidently determine whether this content was AI-generated or human-written. This result should not be considered definitive and may require human review. |
| `0.55 – 1.00` | Likely AI-Generated  | Our system found strong evidence that this content was generated by artificial intelligence. Confidence: High.                                         |

All three variants are reachable: the human and AI examples in the [Example Results](#example-results) table produce the Human and AI labels, and the formal-human example produces the Uncertain label.

---

## API Endpoints

### `POST /submit`

Rate limited to 10 requests/minute and 100/day.

**Request**

```json
{
  "creator_id": "test-user-1",
  "text": "Sample writing..."
}
```

**Response**

```json
{
  "content_id": "72387cb2-17ac-4193-b91d-05819e359be2",
  "attribution": "likely_ai",
  "confidence": 0.6095,
  "label": "Likely AI-Generated",
  "label_detail": "Our system found strong evidence that this content was generated by artificial intelligence. Confidence: High.",
  "llm_score": 0.8,
  "stylometric_score": 0.4189
}
```

The `label`/`label_detail` text changes with the confidence score — one of the three variants below — so the label is never the same regardless of score.

Returns HTTP 400 if `text` or `creator_id` is missing or invalid. Returns HTTP 429 when the rate limit is exceeded (see [Rate Limiting](#rate-limiting)).

### `POST /appeal`

**Request**

```json
{
  "content_id": "72387cb2-17ac-4193-b91d-05819e359be2",
  "creator_reasoning": "I wrote this myself."
}
```

**Response**

```json
{
  "content_id": "72387cb2-17ac-4193-b91d-05819e359be2",
  "status": "under_review",
  "message": "Your appeal was received and is under review."
}
```

### `GET /log`

Returns the most recent structured audit log entries as JSON.

```json
{ "entries": [ /* ... */ ] }
```

---

## Rate Limiting

The `POST /submit` endpoint is rate limited with [Flask-Limiter](https://flask-limiter.readthedocs.io/) (keyed by client IP, in-memory storage) to:

```text
10 per minute; 100 per day
```

**Reasoning.** The limits are sized for the real user — a writer submitting their own work — while blocking a script flooding the system:

- **10/minute** comfortably covers a person pasting and re-checking several drafts in a sitting, but a flood script hits the ceiling almost immediately. Each submit also makes a paid Groq API call, so a per-minute cap directly bounds cost and protects the upstream quota.
- **100/day** is generous for legitimate individual use (few people genuinely classify 100 distinct pieces of writing in a day) yet caps sustained abuse that stays under the per-minute limit.

When a limit is exceeded the endpoint returns **HTTP 429**.

### 429 Evidence

Sending 12 rapid requests (more than the 10/minute limit) in a fresh minute produces 10× `200` then `429` for the rest:

```text
200
200
200
200
200
200
200
200
200
200
429
429
```

(Generated with the loop below; the exact split depends on how many of the minute's 10 submits were already used.)

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5000/submit \
    -H "Content-Type: application/json" \
    -d '{"text": "This is a test submission for rate limit testing purposes only.", "creator_id": "ratelimit-test"}'
done
```

---

## Audit Log

Every submission and appeal writes a structured JSON entry (one JSON object per line) to `audit_log.jsonl`. Each entry captures the timestamp, content ID, attribution result, confidence score, both individual signal scores, and whether an appeal has been filed.

A **classification** entry:

```json
{
  "event": "classification",
  "content_id": "72387cb2-17ac-4193-b91d-05819e359be2",
  "creator_id": "u1",
  "attribution": "likely_ai",
  "confidence": 0.6095,
  "llm_score": 0.8,
  "stylometric_score": 0.4189,
  "label": "Likely AI-Generated",
  "status": "classified",
  "appeal_filed": false,
  "timestamp": "2026-06-27T03:22:38.133375+00:00"
}
```

An **appeal** entry links back to the original decision (carrying over the attribution, confidence, and both signal scores) and records the creator's reasoning:

```json
{
  "event": "appeal",
  "content_id": "72387cb2-17ac-4193-b91d-05819e359be2",
  "creator_id": "u1",
  "attribution": "likely_ai",
  "confidence": 0.6095,
  "llm_score": 0.8,
  "stylometric_score": 0.4189,
  "label": "Likely AI-Generated",
  "appeal_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker...",
  "appeal_filed": true,
  "status": "under_review",
  "timestamp": "2026-06-27T03:22:39.500000+00:00"
}
```

The `/appeal` endpoint verifies the submission exists (returns **HTTP 404** if not) before logging.

---

## Example Results

Tested across the confidence range with both signal scores recorded:

| Input                 | Groq | Stylometric | Confidence | Label                |
| --------------------- | ---: | ----------: | ---------: | -------------------- |
| Clearly AI-generated  | 0.80 |        0.42 |     0.6095 | Likely AI-Generated  |
| Clearly human-written | 0.20 |        0.08 |     0.1412 | Likely Human-Written |
| Formal human writing  | 0.80 |        0.26 |     0.5302 | Uncertain Result     |
| Lightly edited AI     | 0.40 |        0.34 |     0.3676 | Likely Human-Written |

The formal-human case landing in **Uncertain** is expected: formal, consistently structured prose triggers AI-leaning signals, and the system deliberately declines to make a high-confidence call rather than risk a false positive.

### Example request

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "The sun dipped below the horizon, painting the sky in hues of amber and rose. I sat on the porch, coffee in hand, watching the neighborhood slowly go quiet.", "creator_id": "test-user-1"}' | python -m json.tool
```

---

## Known Limitations

**Formal, non-native, or technical human writing is the content this system would
most likely get wrong** — and it would get it wrong by leaning *toward* a false
"AI" call. This is not a "needs more data" problem; it is a direct property of both
signals.

- The **stylometric signal** equates regularity with machine authorship. Its three
  metrics all reward *variation*: high sentence-length variance, diverse vocabulary,
  irregular punctuation. But a non-native English speaker, a careful academic, or a
  technical writer naturally produces *low-variation* prose — even sentence lengths,
  a controlled vocabulary, consistent comma usage. Those are exactly the features the
  metrics score as AI-like, even though they are hallmarks of disciplined human
  writing. The signal literally cannot tell "polished and consistent because a human
  worked at it" apart from "consistent because a model generated it."
- The **Groq LLM signal** compounds this. In testing, formal human prose (the
  monetary-policy sample) drew a Groq score of `0.80–0.90` because formal register
  *correlates* with the AI patterns the model was prompted to look for. Both signals
  then point the same wrong direction, and the average lands in or above the Uncertain
  band rather than safely in "human."

The system partly mitigates this with the Uncertain band — the formal-human sample
resolves to "Uncertain Result" rather than a confident false positive — but a writer
whose only crime is writing cleanly still does not get the "Likely Human-Written"
label they deserve. Two related weaknesses follow from the same root: **very short
text** (a tweet, one sentence) gives the stylometric metrics too little to measure,
and **poetry / song lyrics** (repetition, broken punctuation) trip the metrics in the
opposite direction. All three trace back to the same fact: the stylometric signal
measures surface regularity, not authorship.

A real deployment would need a calibrated, confidence-aware model trained on labeled
human/AI pairs (including non-native and technical writing) before any of these
outputs should carry weight in a consequential decision.

---

## Spec Reflection

**One way the spec guided the implementation.** The `planning.md` spec defined the
**Uncertainty Representation** table — the exact confidence bands, attribution
levels, and the rule that false positives are worse than false negatives — *before*
any scoring code existed. That table drove the implementation directly:
`classify()` and `generate_label()` in [app.py](app.py) are a near-literal
transcription of it, and the narrow Uncertain band (`0.46–0.54`) exists because the
spec committed to "prefer Uncertain over a wrong confident call" up front. Having the
decision boundaries fixed in the spec meant the scoring code was a translation task,
not a series of arbitrary in-the-moment choices.

**One way the implementation diverged.** The spec describes the Uncertain category as
triggering "whenever the two signals disagree significantly." The implementation does
**not** measure signal disagreement directly — there is no `abs(groq - stylometric)`
term. Instead, disagreement is handled *implicitly*: when the two signals diverge,
the equal-weight average mathematically pulls the combined score toward the middle,
into the Uncertain band. I chose this because an explicit disagreement threshold would
have added a second tunable parameter with no data to tune it against, and the simple
average already produces the intended behavior (the formal-human case lands in
Uncertain precisely because Groq `0.90` and stylometry `0.17` average to `0.53`). The
spec's *intent* is satisfied; the *mechanism* is simpler than the spec implied.

---

## AI Usage

**1. Stylometric metric normalization.** I directed the AI to implement the three
stylometric metrics (sentence-length variance, type-token ratio, punctuation rate)
and normalize each to a `0.0–1.0` AI-likeness score. It produced working code, but
its first version used unbounded raw ratios and computed type-token ratio over the
*entire* text. I overrode both: TTR is length-sensitive (longer text mechanically
lowers it), so I had it cap the window at the first 100 words, and I added explicit
`_clamp01()` calls and documented cutoff thresholds (e.g. std-dev 3→9 words) so each
metric maps to a defined, inspectable range. I also annotated TTR in the code as a
weak discriminator on short inputs, which the AI had not flagged.

**2. Rate limiting and the 429 path.** I asked the AI to add rate limiting to
`/submit`. It produced a Flask-Limiter setup but initially applied a single global
default limit. I revised this to a dual `10 per minute; 100 per day` limit scoped
to the `/submit` route specifically, because the two limits protect against different
things (per-minute bounds Groq API cost and bursts; per-day caps sustained abuse) —
reasoning I added to the README rather than accepting the generic single-limit
default the AI generated.

**3. README reasoning sections (this milestone).** I directed the AI to draft the
"why these signals," "why a simple average," and limitations sections. It tended to
write generic, optimistic explanations; I revised them to tie every claim to a
concrete property of the code (e.g. that the stylometric signal "measures surface
regularity, not authorship") and to cite real scores lifted from `audit_log.jsonl`
rather than illustrative made-up numbers.

Loom Walkthrough: 

https://www.loom.com/share/01b7ab149ee647e9bf5c1a525ec8f752
